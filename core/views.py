from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Q, Count
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_POST
from firebase_admin import auth as firebase_auth
from .models import (
    VehicleListing,
    VehiclePhoto,
    Notification,
    UserProfile,
    ContactInquiry,
    ChatConversation,
    ChatMessage,
)
from django.db import IntegrityError
from django.urls import reverse
from .forms import SignUpForm, ProfileEditForm, VehicleListingForm, VehiclePhotoForm, ContactInquiryForm, SearchFilterForm
from firebase_admin import auth as firebase_auth
from .firebase_utils import firebase_verify_password, send_firebase_verification_email, firebase_is_email_verified
from functools import wraps
# ─── EMAIL VERIFICATION GATE ──────────────────────────────────────────────────
def email_verified_required(view_func):
    """
    Blocks an action (posting a listing, contacting a seller, etc.) until the
    user's email is verified. Sends them to the verify-email page instead.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.email_verified:
            messages.warning(
                request,
                "Please verify your email address first — this helps keep AutoHub safe for everyone."
            )
            return redirect('verify_email')
        return view_func(request, *args, **kwargs)
    return wrapper


# ─── PUBLIC HOMEPAGE ──────────────────────────────────────────────────────────
def home(request):
    featured = VehicleListing.objects.filter(is_active=True, is_approved=True).order_by('-created_at')[:6]
    for_sale = VehicleListing.objects.filter(is_active=True, is_approved=True, listing_type='sale').count()
    for_rent = VehicleListing.objects.filter(is_active=True, is_approved=True, listing_type='rent').count()
    total_users = User.objects.count()
    return render(request, 'core/home.html', {
        'featured': featured,
        'for_sale': for_sale,
        'for_rent': for_rent,
        'total_users': total_users,
    })


# ─── ABOUT PAGE ───────────────────────────────────────────────────────────────
def about(request):
    return render(request, 'core/about.html')


# ─── SIGN UP ──────────────────────────────────────────────────────────────────
def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    if request.method == 'POST':
        form = SignUpForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                user = form.save()
            except ValidationError as e:
                for error in e.messages:
                    form.add_error(None, error)
            else:
                login(request, user)
                send_firebase_verification_email(user.email)
                messages.success(
                    request,
                    f"Welcome to AutoHub, {user.first_name}! We've sent a verification link to "
                    f"{user.email} — please confirm it before posting, buying/renting, or "
                    "messaging sellers."
                )
                return redirect('verify_email')
    else:
        form = SignUpForm()
    return render(request, 'core/signup.html', {'form': form})


# ─── LOGIN ────────────────────────────────────────────────────────────────────
def login_view(request):
    """
    Log in using the role already stored on the user's profile.

    The login form intentionally does NOT ask the user to choose Customer or
    Seller. The role is an account property selected during signup (or changed
    later by the Become a Seller flow).
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = AuthenticationForm(request, data=request.POST)
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')

        try:
            django_user = User.objects.get(username=username)
        except User.DoesNotExist:
            django_user = None

        if django_user and django_user.email:
            profile = UserProfile.objects.filter(user=django_user).first()

            # Normal Firebase-backed accounts are authenticated by Firebase.
            # Older/local accounts with no Firebase UID can still use their
            # Django password, which prevents those accounts from becoming
            # impossible to log into after the Firebase migration.
            firebase_uid = None
            if profile and profile.firebase_uid:
                firebase_uid = firebase_verify_password(django_user.email, password)
            else:
                authenticated_user = authenticate(request, username=username, password=password)
                if authenticated_user == django_user:
                    firebase_uid = 'django-fallback'

            if firebase_uid:
                django_user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, django_user)
                role_label = (
                    dict(UserProfile.ROLE_CHOICES).get(profile.role, profile.role)
                    if profile else 'Customer'
                )
                messages.success(
                    request,
                    f"Welcome back, {django_user.first_name or django_user.username}! "
                    f"Signed in as {role_label}."
                )
                return redirect('dashboard')

        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()

    return render(request, 'core/login.html', {'form': form})


# ─── VERIFY EMAIL ─────────────────────────────────────────────────────────────
@login_required
def verify_email_view(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        # "Resend verification email"
        if send_firebase_verification_email(request.user.email):
            messages.success(request, "Verification email sent — please check your inbox.")
        else:
            messages.error(request, "We couldn't send the verification email right now. Please try again shortly.")
        return redirect('verify_email')

    # GET (including the "I've Verified — Check Again" link): re-check Firebase's
    # live status and sync it onto the profile.
    if not profile.email_verified:
        live_status = firebase_is_email_verified(profile.firebase_uid)
        if live_status is True:
            profile.email_verified = True
            profile.save(update_fields=['email_verified'])
            messages.success(request, "Your email is verified! You now have full access to AutoHub.")
        elif live_status is False:
            messages.info(request, "Your email isn't verified yet. Check your inbox for the verification link.")
        # live_status is None (e.g. lookup failed) — just show the current known status

    return render(request, 'core/verify_email.html', {'email_verified': profile.email_verified})


# ─── FORGOT PASSWORD (Firebase email-link reset) ────────────────────────────
def forgot_password_view(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        try:
            link = firebase_auth.generate_password_reset_link(
                email,
                # action_code_settings=firebase_auth.ActionCodeSettings(
                #     url='localhost',  # update to your real domain in prod
                #     handle_code_in_app=False,
                # )
            )
            send_mail(
                subject="Reset your AutoHub password",
                message=(
                    f"Hi,\n\nClick the link below to reset your AutoHub password:\n\n{link}\n\n"
                    "If you didn't request this, you can safely ignore this email."
                ),
                from_email=None,  # uses DEFAULT_FROM_EMAIL
                recipient_list=[email],
            )
        except Exception as e:
            # Don't reveal whether the email exists — same page renders either way
            print(f"[Firebase] password reset link failed for {email}: {e}")

        return render(request, 'core/forgot_password_done.html', {'email': email})

    return render(request, 'core/forgot_password.html')



# ─── LOGOUT ───────────────────────────────────────────────────────────────────
@login_required
def logout_view(request):
    logout(request)
    messages.info(request, "You have been logged out.")
    return redirect('home')


# ─── USER DASHBOARD ───────────────────────────────────────────────────────────
@login_required
def dashboard(request):
    form = SearchFilterForm(request.GET)
    listings = VehicleListing.objects.filter(is_active=True, is_approved=True)

    if form.is_valid():
        q = form.cleaned_data.get('q')
        listing_type = form.cleaned_data.get('listing_type')
        brand = form.cleaned_data.get('brand')
        fuel_type = form.cleaned_data.get('fuel_type')
        min_price = form.cleaned_data.get('min_price')
        max_price = form.cleaned_data.get('max_price')

        if q:
            listings = listings.filter(
                Q(brand__icontains=q) | Q(model__icontains=q) |
                Q(description__icontains=q) | Q(pickup_location__icontains=q)
            )
        if listing_type:
            listings = listings.filter(listing_type=listing_type)
        if brand:
            listings = listings.filter(brand=brand)
        if fuel_type:
            listings = listings.filter(fuel_type=fuel_type)
        if min_price:
            listings = listings.filter(price__gte=min_price)
        if max_price:
            listings = listings.filter(price__lte=max_price)

    listings = listings.order_by('-created_at')
    return render(request, 'core/dashboard.html', {'listings': listings, 'form': form})


# ─── VEHICLE DETAIL ───────────────────────────────────────────────────────────

@login_required
def vehicle_detail(request, pk):
    """Display a vehicle and its private buyer/seller chat."""

    listing = get_object_or_404(
        VehicleListing,
        pk=pk,
        is_active=True,
    )

    if (
        not listing.is_approved
        and listing.owner != request.user
        and not is_admin(request.user)
    ):
        raise Http404("Listing not found.")

    inquiry_form = ContactInquiryForm()
    conversation = None
    chat_messages = []
    conversations = []
    selected_conversation = None

    # Chat is available only to verified, authenticated users.
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        if profile.email_verified:
            if request.user != listing.owner:
                # One private conversation per buyer for this vehicle.
                conversation, _ = ChatConversation.objects.get_or_create(
                    listing=listing,
                    customer=request.user,
                )
                chat_messages = conversation.messages.select_related(
                    'sender'
                ).all()

                # Seller messages become read when the buyer opens the listing.
                conversation.messages.filter(
                    sender=listing.owner,
                    is_read=False,
                ).update(is_read=True)

            else:
                # Seller sees all buyers who have contacted this vehicle,
                # directly inside the vehicle detail page.
                conversations = list(
                    ChatConversation.objects.filter(
                        listing=listing
                    ).select_related(
                        'customer'
                    ).prefetch_related(
                        'messages'
                    ).order_by('-updated_at')
                )

                selected_id = request.GET.get('conversation')
                if selected_id:
                    selected_conversation = get_object_or_404(
                        ChatConversation,
                        pk=selected_id,
                        listing=listing,
                    )
                elif conversations:
                    selected_conversation = conversations[0]

                if selected_conversation:
                    selected_conversation.messages.filter(
                        sender=selected_conversation.customer,
                        is_read=False,
                    ).update(is_read=True)
                    chat_messages = selected_conversation.messages.select_related(
                        'sender'
                    ).all()

    # Keep the existing inquiry form for compatibility with older pages.
    if request.method == 'POST' and request.POST.get('inquiry_message'):
        if not request.user.is_authenticated:
            return redirect('login')

        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        if not profile.email_verified:
            messages.warning(
                request,
                "Please verify your email address before contacting a seller."
            )
            return redirect('verify_email')

        inquiry_form = ContactInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.sender = request.user
            inquiry.save()

            Notification.objects.create(
                recipient=listing.owner,
                notif_type='message',
                title=f"New inquiry on your {listing.brand} {listing.model}",
                message=f"{request.user.username} sent: {inquiry.message[:100]}",
                related_listing=listing,
            )

            messages.success(request, "Your inquiry has been sent!")
            return redirect('vehicle_detail', pk=pk)

    return render(
        request,
        'core/vehicle_detail.html',
        {
            'listing': listing,
            'inquiry_form': inquiry_form,
            'conversation': conversation,
            'conversations': conversations,
            'selected_conversation': selected_conversation,
            'chat_messages': chat_messages,
        }
    )


# ─── SEND CHAT MESSAGE ────────────────────────────────────────────────────────

@login_required
@email_verified_required
@require_POST
def send_chat_message(request, pk):
    """
    Send a message in the private conversation for this vehicle.

    Buyers send to the seller. Sellers can reply to a selected buyer
    from the same vehicle detail page.
    """

    listing = get_object_or_404(
        VehicleListing,
        pk=pk,
        is_active=True,
        is_approved=True,
    )

    message_text = request.POST.get('message', '').strip()

    if not message_text:
        messages.warning(request, "Please enter a message.")
        return redirect('vehicle_detail', pk=listing.pk)

    if len(message_text) > 2000:
        messages.warning(
            request,
            "Your message is too long. Please keep it under 2000 characters."
        )
        return redirect('vehicle_detail', pk=listing.pk)

    if request.user == listing.owner:
        # Seller must choose which buyer they are replying to.
        conversation_id = request.POST.get('conversation_id')
        if not conversation_id:
            messages.warning(request, "Please select a conversation first.")
            return redirect('vehicle_detail', pk=listing.pk)

        conversation = get_object_or_404(
            ChatConversation,
            pk=conversation_id,
            listing=listing,
        )
    else:
        # Buyer always uses their own conversation for this vehicle.
        conversation, _ = ChatConversation.objects.get_or_create(
            listing=listing,
            customer=request.user,
        )

    ChatMessage.objects.create(
        conversation=conversation,
        sender=request.user,
        message=message_text,
    )
    conversation.save()

    recipient = (
        conversation.customer
        if request.user == listing.owner
        else listing.owner
    )

    Notification.objects.create(
        recipient=recipient,
        notif_type='message',
        title='New vehicle chat message',
        message=(
            f"{request.user.get_full_name() or request.user.username} "
            f"sent a message about the "
            f"{listing.year} {listing.brand} {listing.model}."
        ),
        related_listing=listing,
    )

    if request.user == listing.owner:
        return redirect(
            f"{reverse('vehicle_detail', kwargs={'pk': listing.pk})}"
            f"?conversation={conversation.id}#vehicle-chat"
        )

    return redirect(
        f"{reverse('vehicle_detail', kwargs={'pk': listing.pk})}#vehicle-chat"
    )


# ─── POST / EDIT VEHICLE ──────────────────────────────────────────────────────
@login_required
@email_verified_required
def post_vehicle(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.role != 'seller':
        messages.error(request, "Only seller accounts can post vehicle listings.")
        return redirect('dashboard')

    if request.method == 'POST':
        form = VehicleListingForm(request.POST)
        photos = request.FILES.getlist('photos')

        if form.is_valid():
            listing = form.save(commit=False)
            listing.owner = request.user
            listing.save()

            for i, photo in enumerate(photos):
                VehiclePhoto.objects.create(
                    listing=listing,
                    image=photo,
                    is_main=(i == 0)
                )

            messages.success(
                request,
                "Your vehicle has been submitted! It will be visible to buyers/renters "
                "once an admin reviews and approves it."
            )
            return redirect('vehicle_detail', pk=listing.pk)
    else:
        form = VehicleListingForm()

    return render(request, 'core/post_vehicle.html', {'form': form})


# ─── EDIT VEHICLE ─────────────────────────────────────────────────────────────
@login_required
def edit_vehicle(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk, owner=request.user)

    if request.method == 'POST':
        form = VehicleListingForm(request.POST, instance=listing)
        photos = request.FILES.getlist('photos')

        if form.is_valid():
            form.save()
            for i, photo in enumerate(photos):
                VehiclePhoto.objects.create(listing=listing, image=photo)
            messages.success(request, "Listing updated successfully!")
            return redirect('vehicle_detail', pk=listing.pk)
    else:
        form = VehicleListingForm(instance=listing)

    return render(request, 'core/post_vehicle.html', {'form': form, 'listing': listing, 'editing': True})


# ─── DELETE VEHICLE ───────────────────────────────────────────────────────────
@login_required
def delete_vehicle(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk, owner=request.user)
    if request.method == 'POST':
        listing.is_active = False
        listing.save()
        messages.success(request, "Listing removed.")
    return redirect('my_profile')


# ─── DELETE PHOTO ─────────────────────────────────────────────────────────────
@login_required
def delete_photo(request, photo_id):
    photo = get_object_or_404(VehiclePhoto, pk=photo_id, listing__owner=request.user)
    listing_pk = photo.listing.pk
    photo.delete()
    return redirect('edit_vehicle', pk=listing_pk)


# ─── MY PROFILE ───────────────────────────────────────────────────────────────
@login_required
def my_profile(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    my_listings = VehicleListing.objects.filter(owner=request.user, is_active=True).order_by('-created_at')

    if request.method == 'POST':
        form = ProfileEditForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            profile = form.save()
            new_email = form.cleaned_data['email']
            email_changed = new_email != request.user.email
            request.user.email = new_email
            request.user.save()

            if email_changed:
                # The old verification no longer applies to the new address.
                if profile.firebase_uid:
                    try:
                        firebase_auth.update_user(profile.firebase_uid, email=new_email)
                    except Exception as e:
                        print(f"[Firebase] failed to update email for uid {profile.firebase_uid}: {e}")
                profile.email_verified = False
                profile.save(update_fields=['email_verified'])
                send_firebase_verification_email(new_email)
                messages.success(
                    request,
                    "Profile updated! Since you changed your email, please verify the new "
                    "address before posting, buying/renting, or messaging sellers."
                )
                return redirect('verify_email')

            messages.success(request, "Profile updated successfully!")
            return redirect('my_profile')
    else:
        form = ProfileEditForm(instance=profile)

    return render(request, 'core/my_profile.html', {
        'form': form,
        'profile': profile,
        'my_listings': my_listings,
    })

# ─── BECOME A SELLER (customer → seller upgrade) ─────────────────────────────
@login_required
def become_seller(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if profile.role == 'seller':
        messages.info(request, "You're already a seller — you can post vehicles anytime!")
        return redirect('post_vehicle')

    if request.method == 'POST':
        profile.role = 'seller'
        profile.save()
        messages.success(request, "You're now a seller! You can start posting vehicles.")
        return redirect('post_vehicle')

    return render(request, 'core/become_seller.html', {'profile': profile})

# ─── NOTIFICATIONS ────────────────────────────────────────────────────────────
@login_required
def notifications(request):
    notifs = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    notifs.filter(is_read=False).update(is_read=True)
    return render(request, 'core/notifications.html', {'notifications': notifs})


# ─── MARK NOTIFICATION READ (AJAX) ───────────────────────────────────────────
@login_required
def mark_notif_read(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    notif.is_read = True
    notif.save()
    return JsonResponse({'status': 'ok'})


# ─── ADMIN DASHBOARD ─────────────────────────────────────────────────────────
def is_admin(user):
    return user.is_staff or user.is_superuser


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    total_users = User.objects.count()
    total_listings = VehicleListing.objects.filter(is_active=True).count()
    for_sale = VehicleListing.objects.filter(is_active=True, listing_type='sale').count()
    for_rent = VehicleListing.objects.filter(is_active=True, listing_type='rent').count()
    recent_users = User.objects.order_by('-date_joined')[:10]
    recent_listings = VehicleListing.objects.filter(is_active=True).order_by('-created_at')[:10]
    unapproved = VehicleListing.objects.filter(is_approved=False, is_active=True)

    return render(request, 'core/admin_dashboard.html', {
        'total_users': total_users,
        'total_listings': total_listings,
        'for_sale': for_sale,
        'for_rent': for_rent,
        'recent_users': recent_users,
        'recent_listings': recent_listings,
        'unapproved': unapproved,
    })


@login_required
@user_passes_test(is_admin)
def admin_listing_review(request, pk):
    """
    Dedicated review page for a single pending (or any) listing — shows every
    field, all photos, and a snapshot of the poster's account, so an admin can
    check for explicit/inappropriate content, obviously wrong or junk data,
    and whether the account itself looks legitimate, all before approving.
    """
    listing = get_object_or_404(VehicleListing, pk=pk)
    owner_profile, _ = UserProfile.objects.get_or_create(user=listing.owner)

    owner_other_listings = VehicleListing.objects.filter(
        owner=listing.owner
    ).exclude(pk=listing.pk).order_by('-created_at')

    context = {
        'listing': listing,
        'owner_profile': owner_profile,
        'owner_other_listings': owner_other_listings,
        'owner_listing_count': VehicleListing.objects.filter(owner=listing.owner, is_active=True).count(),
        'owner_removed_count': VehicleListing.objects.filter(owner=listing.owner, is_active=False).count(),
    }
    return render(request, 'core/admin_listing_review.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_approve_listing(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk)
    listing.is_approved = True
    listing.save()
    Notification.objects.create(
        recipient=listing.owner,
        notif_type='update',
        title='Your listing was approved',
        message=f'Your {listing.year} {listing.brand} {listing.model} is now live on AutoHub.',
        related_listing=listing,
    )
    messages.success(request, f"Listing '{listing}' approved.")
    next_url = request.POST.get('next') or 'admin_dashboard'
    return redirect(next_url)


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_remove_listing(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk)
    was_pending = not listing.is_approved
    listing.is_active = False
    listing.save()
    Notification.objects.create(
        recipient=listing.owner,
        notif_type='update',
        title='Your listing was not approved' if was_pending else 'Your listing was removed',
        message=(
            f'Your {listing.year} {listing.brand} {listing.model} did not meet AutoHub\'s '
            'listing guidelines and was not published.'
            if was_pending else
            f'Your {listing.year} {listing.brand} {listing.model} was removed by an admin.'
        ),
        related_listing=listing,
    )
    messages.success(request, f"Listing '{listing}' removed.")
    next_url = request.POST.get('next') or 'admin_dashboard'
    return redirect(next_url)


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'core/admin_users.html', {'users': users})