from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Q, Count, Prefetch
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
    SellerRating,
    VehicleRating,
)
from django.db import IntegrityError
from django.urls import reverse
from .forms import (
    SignUpForm,
    ProfileEditForm,
    VehicleListingForm,
    VehiclePhotoForm,
    ContactInquiryForm,
    SearchFilterForm,
    SellerRatingForm,
    VehicleRatingForm,
    SellerIDVerificationForm,
)
from django.utils import timezone
from django.template.defaultfilters import linebreaksbr, date as date_filter
from .supabase_utils import upload_id_document, get_signed_id_url, delete_id_document
from firebase_admin import auth as firebase_auth
from .firebase_utils import firebase_verify_password, send_firebase_verification_email, firebase_is_email_verified
from .email_utils import send_email
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
                email_sent = send_firebase_verification_email(user.email)
                if email_sent:
                    messages.success(
                        request,
                        f"Welcome to AutoHub, {user.first_name}! We've sent a verification link to "
                        f"{user.email} — please confirm it before posting, buying/renting, or "
                        "messaging sellers."
                    )
                else:
                    messages.warning(
                        request,
                        f"Welcome to AutoHub, {user.first_name}! Your account is created, but we "
                        "couldn't send the verification email just now. Please use the "
                        "\"Resend\" button below to try again."
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
            send_email(
                subject="Reset your AutoHub password",
                body=(
                    f"Hi,\n\nClick the link below to reset your AutoHub password:\n\n{link}\n\n"
                    "If you didn't request this, you can safely ignore this email."
                ),
                to_email=email,
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
    listings = VehicleListing.objects.filter(
        is_active=True, is_approved=True
    ).prefetch_related(
        Prefetch('photos', queryset=VehiclePhoto.objects.order_by('pk'))
    )

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
    unread_chat_count = 0

    # The chat itself is loaded by the floating chat panel through
    # chat_poll(); here we only need the unread count for the bubble badge.
    if request.user.is_authenticated:
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        if profile.email_verified:
            unread_chat_count = _unread_chat_messages(
                listing, request.user
            ).count()

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

    # ── Seller/renter account ratings (trust ratings on the person) ──
    seller_ratings = SellerRating.objects.filter(
        seller=listing.owner
    ).select_related('rater')[:20]

    user_seller_rating = None
    seller_rating_form = SellerRatingForm()

    # ── Per-vehicle ratings (only meaningful for rental listings) ──
    vehicle_ratings = []
    user_vehicle_rating = None
    vehicle_rating_form = VehicleRatingForm()

    if request.user.is_authenticated and request.user != listing.owner:
        user_seller_rating = SellerRating.objects.filter(
            seller=listing.owner, rater=request.user
        ).first()
        if user_seller_rating:
            seller_rating_form = SellerRatingForm(instance=user_seller_rating)

        if listing.listing_type == 'rent':
            user_vehicle_rating = VehicleRating.objects.filter(
                listing=listing, rater=request.user
            ).first()
            if user_vehicle_rating:
                vehicle_rating_form = VehicleRatingForm(instance=user_vehicle_rating)

    if listing.listing_type == 'rent':
        vehicle_ratings = listing.vehicle_ratings.select_related('rater')[:20]

    return render(
        request,
        'core/vehicle_detail.html',
        {
            'listing': listing,
            'inquiry_form': inquiry_form,
            'unread_chat_count': unread_chat_count,
            'seller_ratings': seller_ratings,
            'user_seller_rating': user_seller_rating,
            'seller_rating_form': seller_rating_form,
            'vehicle_ratings': vehicle_ratings,
            'user_vehicle_rating': user_vehicle_rating,
            'vehicle_rating_form': vehicle_rating_form,
        }
    )


# ─── CHAT HELPERS ─────────────────────────────────────────────────────────────

def _is_ajax(request):
    return request.headers.get('X-Requested-With') == 'XMLHttpRequest'


def _unread_chat_messages(listing, user):
    """
    Messages about this listing that `user` has received but not read yet.

    Owner: unread messages from every buyer.  Buyer: unread replies in their
    own conversation only.
    """
    qs = ChatMessage.objects.filter(
        conversation__listing=listing,
        is_read=False,
    ).exclude(sender=user)

    if user != listing.owner:
        qs = qs.filter(conversation__customer=user)

    return qs


def _serialize_chat_message(msg, viewer):
    return {
        'id': msg.id,
        'mine': msg.sender_id == viewer.id,
        # linebreaksbr escapes the text first, so this is safe to inject.
        'html': linebreaksbr(msg.message),
        'time': date_filter(msg.created_at, 'M d, Y g:i A'),
    }


def _chat_error(request, listing, text, status=400):
    if _is_ajax(request):
        return JsonResponse({'ok': False, 'error': text}, status=status)
    messages.warning(request, text)
    return redirect('vehicle_detail', pk=listing.pk)


# ─── SEND CHAT MESSAGE ────────────────────────────────────────────────────────

@login_required
@email_verified_required
@require_POST
def send_chat_message(request, pk):
    """
    Send a message in the private conversation for this vehicle.

    Buyers send to the seller. Sellers reply to a selected buyer.
    Returns JSON for AJAX requests (no page reload), otherwise redirects.
    """

    listing = get_object_or_404(
        VehicleListing,
        pk=pk,
        is_active=True,
        is_approved=True,
    )

    message_text = request.POST.get('message', '').strip()

    if not message_text:
        return _chat_error(request, listing, "Please enter a message.")

    if len(message_text) > 2000:
        return _chat_error(
            request,
            listing,
            "Your message is too long. Please keep it under 2000 characters."
        )

    if request.user == listing.owner:
        # Seller must choose which buyer they are replying to.
        conversation_id = request.POST.get('conversation_id')
        if not conversation_id:
            return _chat_error(
                request, listing, "Please select a conversation first."
            )

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

    chat_message = ChatMessage.objects.create(
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

    if _is_ajax(request):
        return JsonResponse({
            'ok': True,
            'conversation_id': conversation.id,
            'message': _serialize_chat_message(chat_message, request.user),
        })

    if request.user == listing.owner:
        return redirect(
            f"{reverse('vehicle_detail', kwargs={'pk': listing.pk})}"
            f"?conversation={conversation.id}#vehicle-chat"
        )

    return redirect(
        f"{reverse('vehicle_detail', kwargs={'pk': listing.pk})}#vehicle-chat"
    )


# ─── CHAT POLL (AJAX) ─────────────────────────────────────────────────────────

@login_required
@email_verified_required
def chat_poll(request, pk):
    """
    Lightweight endpoint the chat panel polls so new messages and unread
    badges show up without reloading the page.

    GET params:
      conversation  owner only; which buyer's thread (defaults to the latest)
      after         only return messages with id greater than this
      mark_read     "1" when the chat panel is open and the user is looking
                    at the thread, so incoming messages count as read
    """

    listing = get_object_or_404(VehicleListing, pk=pk, is_active=True)
    is_owner = request.user == listing.owner

    conversations_payload = []
    conversation = None

    if is_owner:
        convs = list(
            ChatConversation.objects.filter(listing=listing)
            .select_related('customer')
            .annotate(
                msg_total=Count('messages'),
                unread=Count(
                    'messages',
                    filter=Q(messages__is_read=False)
                    & ~Q(messages__sender=listing.owner),
                ),
            )
            .filter(msg_total__gt=0)
            .order_by('-updated_at')
        )

        conversations_payload = [
            {
                'id': c.id,
                'name': c.customer.get_full_name() or c.customer.username,
                'unread': c.unread,
            }
            for c in convs
        ]

        requested = request.GET.get('conversation', '')
        if requested.isdigit():
            conversation = next(
                (c for c in convs if c.id == int(requested)), None
            )
        if conversation is None and convs:
            conversation = convs[0]
    else:
        conversation = ChatConversation.objects.filter(
            listing=listing, customer=request.user
        ).first()

    try:
        after = int(request.GET.get('after', 0))
    except (TypeError, ValueError):
        after = 0

    new_messages = []
    if conversation:
        new_messages = [
            _serialize_chat_message(m, request.user)
            for m in conversation.messages.filter(id__gt=after)
        ]

        if request.GET.get('mark_read') == '1':
            conversation.messages.filter(is_read=False).exclude(
                sender=request.user
            ).update(is_read=True)

            # Keep the per-conversation badge in sync with what we just read.
            for c in conversations_payload:
                if c['id'] == conversation.id:
                    c['unread'] = 0

    return JsonResponse({
        'conversation_id': conversation.id if conversation else None,
        'messages': new_messages,
        'conversations': conversations_payload,
        'unread_total': _unread_chat_messages(
            listing, request.user
        ).count(),
        # Lets the nav-bar bell stay accurate without a reload too.
        'unread_notifications': Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count(),
    })


# ─── GLOBAL CHAT WIDGET (inbox / thread / send) ──────────────────────────────
# These power the floating chat bubble that appears on every page for users
# who already have at least one conversation.

def _display_name(user):
    return user.get_full_name() or user.username


def _avatar_url(user):
    profile = getattr(user, 'profile', None)
    pic = getattr(profile, 'profile_picture', None) if profile else None
    try:
        return pic.url if pic else ''
    except ValueError:
        return ''


def _user_conversations(user):
    """Conversations `user` takes part in (as buyer or as listing owner)."""
    return ChatConversation.objects.filter(
        Q(customer=user) | Q(listing__owner=user)
    )


def _unread_chat_total(user):
    """Every chat message waiting for `user` across all conversations."""
    return ChatMessage.objects.filter(
        is_read=False,
    ).filter(
        Q(conversation__customer=user) | Q(conversation__listing__owner=user)
    ).exclude(sender=user).count()


def _get_participant_conversation(request, conv_id):
    conv = get_object_or_404(
        ChatConversation.objects.select_related('listing__owner', 'customer'),
        pk=conv_id,
    )
    if request.user not in (conv.customer, conv.listing.owner):
        raise Http404("Conversation not found.")
    return conv


@login_required
@email_verified_required
def chat_inbox(request):
    """JSON list of the user's conversations, newest first."""
    user = request.user
    convs = (
        _user_conversations(user)
        .select_related('listing__owner__profile', 'customer__profile')
        .annotate(
            msg_total=Count('messages', distinct=True),
            unread=Count(
                'messages',
                filter=Q(messages__is_read=False) & ~Q(messages__sender=user),
                distinct=True,
            ),
        )
        .filter(msg_total__gt=0)
        .order_by('-updated_at')[:50]
    )

    payload = []
    for c in convs:
        as_seller = c.listing.owner_id == user.id
        other = c.customer if as_seller else c.listing.owner
        last = c.messages.order_by('-created_at').first()
        listing = c.listing
        payload.append({
            'id': c.id,
            'listing_id': listing.id,
            'listing_title': f"{listing.year} {listing.brand} {listing.model}",
            'listing_url': reverse('vehicle_detail', kwargs={'pk': listing.pk}),
            'other_name': _display_name(other),
            'other_avatar': _avatar_url(other),
            'as_seller': as_seller,
            'preview': (last.message[:80] if last else ''),
            'last_mine': bool(last and last.sender_id == user.id),
            'time': date_filter(c.updated_at, 'M d, g:i A'),
            'unread': c.unread,
        })

    return JsonResponse({
        'conversations': payload,
        'unread_total': _unread_chat_total(user),
        'unread_notifications': Notification.objects.filter(
            recipient=user, is_read=False
        ).count(),
    })


@login_required
@email_verified_required
def chat_thread(request, conv_id):
    """New messages in one conversation (polled by the widget)."""
    conv = _get_participant_conversation(request, conv_id)

    try:
        after = int(request.GET.get('after', 0))
    except (TypeError, ValueError):
        after = 0

    new_messages = [
        _serialize_chat_message(m, request.user)
        for m in conv.messages.filter(id__gt=after)
    ]

    if request.GET.get('mark_read') == '1':
        conv.messages.filter(is_read=False).exclude(
            sender=request.user
        ).update(is_read=True)

    return JsonResponse({
        'messages': new_messages,
        'unread_total': _unread_chat_total(request.user),
        'unread_notifications': Notification.objects.filter(
            recipient=request.user, is_read=False
        ).count(),
    })


@login_required
@email_verified_required
@require_POST
def chat_send(request, conv_id):
    """Send a message into an existing conversation from the widget."""
    conv = _get_participant_conversation(request, conv_id)
    listing = conv.listing

    text = request.POST.get('message', '').strip()
    if not text:
        return JsonResponse({'ok': False, 'error': 'Please enter a message.'}, status=400)
    if len(text) > 2000:
        return JsonResponse({
            'ok': False,
            'error': 'Your message is too long. Please keep it under 2000 characters.',
        }, status=400)

    chat_message = ChatMessage.objects.create(
        conversation=conv,
        sender=request.user,
        message=text,
    )
    conv.save()  # bumps updated_at so it moves to the top of the inbox

    recipient = conv.customer if request.user == listing.owner else listing.owner
    Notification.objects.create(
        recipient=recipient,
        notif_type='message',
        title='New vehicle chat message',
        message=(
            f"{_display_name(request.user)} sent a message about the "
            f"{listing.year} {listing.brand} {listing.model}."
        ),
        related_listing=listing,
    )

    return JsonResponse({
        'ok': True,
        'conversation_id': conv.id,
        'message': _serialize_chat_message(chat_message, request.user),
    })


# ─── RATE SELLER / RENTER ACCOUNT ─────────────────────────────────────────────
@login_required
@email_verified_required
@require_POST
def rate_seller(request, user_id):
    """
    Leave (or update) a trust rating on a seller/renter's ACCOUNT. Anyone
    logged-in and verified can rate any seller except themselves; submitting
    again simply updates their existing rating (one rating per rater/seller).
    """
    seller = get_object_or_404(User, pk=user_id)

    if seller == request.user:
        messages.error(request, "You can't rate your own account.")
        return redirect('dashboard')

    listing = None
    listing_id = request.POST.get('listing_id')
    if listing_id:
        listing = VehicleListing.objects.filter(pk=listing_id).first()

    existing = SellerRating.objects.filter(seller=seller, rater=request.user).first()
    form = SellerRatingForm(request.POST, instance=existing)

    if form.is_valid():
        rating = form.save(commit=False)
        rating.seller = seller
        rating.rater = request.user
        if listing:
            rating.listing = listing
        rating.save()

        messages.success(
            request,
            f"Thanks — your rating for {seller.first_name or seller.username} has been saved."
        )

        if not existing:
            Notification.objects.create(
                recipient=seller,
                notif_type='system',
                title='You received a new rating',
                message=(
                    f"{request.user.get_full_name() or request.user.username} "
                    f"rated you {rating.score}/5 as a seller/renter."
                ),
                related_listing=listing,
            )
    else:
        messages.error(request, "Please choose a rating from 1 to 5 stars.")

    next_url = request.POST.get('next')
    if listing:
        return redirect(f"{reverse('vehicle_detail', kwargs={'pk': listing.pk})}#reviews")
    return redirect(next_url or 'dashboard')


# ─── RATE A RENTAL VEHICLE LISTING ─────────────────────────────────────────────
@login_required
@email_verified_required
@require_POST
def rate_vehicle(request, pk):
    """
    Leave (or update) a rating on a specific FOR-RENT vehicle listing, based
    on the renter's experience with that particular vehicle. Kept separate
    from the seller/renter account rating above.
    """
    listing = get_object_or_404(VehicleListing, pk=pk, is_active=True)

    if listing.listing_type != 'rent':
        messages.error(request, "Only rental vehicles can be rated for the rental experience.")
        return redirect('vehicle_detail', pk=pk)

    if listing.owner == request.user:
        messages.error(request, "You can't rate your own vehicle listing.")
        return redirect('vehicle_detail', pk=pk)

    existing = VehicleRating.objects.filter(listing=listing, rater=request.user).first()
    form = VehicleRatingForm(request.POST, instance=existing)

    if form.is_valid():
        rating = form.save(commit=False)
        rating.listing = listing
        rating.rater = request.user
        rating.save()

        messages.success(request, "Thanks — your rating for this vehicle has been saved.")

        if not existing:
            Notification.objects.create(
                recipient=listing.owner,
                notif_type='system',
                title='Your vehicle received a new rating',
                message=(
                    f"{request.user.get_full_name() or request.user.username} rated the "
                    f"{listing.year} {listing.brand} {listing.model} {rating.score}/5."
                ),
                related_listing=listing,
            )
    else:
        messages.error(request, "Please choose a rating from 1 to 5 stars.")

    return redirect(f"{reverse('vehicle_detail', kwargs={'pk': pk})}#reviews")


# ─── UPDATE LISTING AVAILABILITY (owner marks rented/sold/available) ─────────
@login_required
@require_POST
def update_listing_status(request, pk):
    """
    Lets the owner flag their own listing as currently rented (for rent
    listings) or sold (for sale listings), or set it back to available.
    Purely informational — doesn't deactivate or hide the listing.
    """
    listing = get_object_or_404(VehicleListing, pk=pk, owner=request.user)
    new_status = request.POST.get('availability_status')

    valid_statuses = (
        ['available', 'rented']
        if listing.listing_type == 'rent'
        else ['available', 'sold']
    )

    if new_status not in valid_statuses:
        messages.error(request, "That status doesn't apply to this type of listing.")
        return redirect('vehicle_detail', pk=pk)

    listing.availability_status = new_status
    listing.save(update_fields=['availability_status'])

    status_label = dict(VehicleListing.AVAILABILITY_CHOICES).get(new_status, new_status)
    messages.success(request, f'Listing marked as "{status_label}".')

    next_url = request.POST.get('next')
    return redirect(next_url or reverse('vehicle_detail', kwargs={'pk': pk}))


# ─── SELLER IDENTITY VERIFICATION ─────────────────────────────────────────────
@login_required
@email_verified_required
def verify_identity(request):
    """
    Sellers upload a government ID (driver's license / national ID) here
    before they're allowed to post vehicles. The file goes straight to a
    private Supabase Storage bucket — it is never saved to Django/Cloudinary
    and never exposed via a public URL.
    """
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if profile.role != 'seller':
        messages.info(request, "Identity verification is only required for seller accounts.")
        return redirect('my_profile')

    # Superusers bypass ID verification entirely.
    if profile.is_id_exempt():
        messages.info(request, "Superuser accounts are exempt from ID verification.")
        return redirect('post_vehicle')

    # Already approved — nothing more to submit. (Re-uploading would reset the
    # status to pending and lock the seller out of posting.)
    if profile.is_id_verified():
        messages.info(request, "Your identity is already verified.")
        return redirect('my_profile')

    if request.method == 'POST':
        form = SellerIDVerificationForm(request.POST, request.FILES)
        if form.is_valid():
            old_path = profile.id_document_path

            path = upload_id_document(
                user_id=request.user.id,
                doc_type=form.cleaned_data['id_document_type'],
                uploaded_file=form.cleaned_data['id_document'],
            )

            if path:
                profile.id_document_type = form.cleaned_data['id_document_type']
                profile.id_document_path = path
                profile.id_verification_status = 'pending'
                profile.id_submitted_at = timezone.now()
                profile.id_reviewed_at = None
                profile.id_rejection_reason = ''
                profile.save()

                if old_path and old_path != path:
                    delete_id_document(old_path)

                messages.success(
                    request,
                    "Your ID was submitted securely. An admin will review it — "
                    "you'll be notified once you're verified and can post vehicles."
                )
                return redirect('my_profile')

            messages.error(
                request,
                "We couldn't upload your ID right now. Please try again in a moment."
            )
    else:
        form = SellerIDVerificationForm(
            initial={'id_document_type': profile.id_document_type or 'drivers_license'}
        )

    return render(request, 'core/verify_identity.html', {
        'form': form,
        'profile': profile,
    })


# ─── POST / EDIT VEHICLE ──────────────────────────────────────────────────────
@login_required
@email_verified_required
def post_vehicle(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    if profile.role != 'seller':
        messages.error(request, "Only seller accounts can post vehicle listings.")
        return redirect('dashboard')

    if not profile.can_post_vehicles():
        if profile.id_verification_status == 'pending':
            messages.info(
                request,
                "Your ID is still being reviewed by an admin. You'll be able to "
                "post vehicles as soon as it's verified."
            )
            return redirect('my_profile')
        messages.warning(
            request,
            "Please verify your identity first — upload a valid government ID "
            "before posting a vehicle. This keeps AutoHub safe for buyers and renters."
        )
        return redirect('verify_identity')

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
    my_listings = list(
        VehicleListing.objects.filter(owner=request.user, is_active=True)
        .prefetch_related('photos')
        .order_by('-created_at')
    )
    # Active = still available; Sold / Rented go to their own tab.
    active_listings = [l for l in my_listings if l.availability_status == 'available']
    closed_listings = [l for l in my_listings if l.availability_status != 'available']

    # Reviews other users have left on this seller's account.
    reviews = list(
        SellerRating.objects.filter(seller=request.user)
        .select_related('rater__profile')
        .order_by('-created_at')
    )
    rating_total = len(reviews)
    rating_avg = round(sum(r.score for r in reviews) / rating_total, 1) if rating_total else 0
    rating_pct = int(round(rating_avg / 5 * 100))

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
        'active_listings': active_listings,
        'closed_listings': closed_listings,
        'reviews': reviews,
        'rating_total': rating_total,
        'rating_avg': rating_avg,
        'rating_pct': rating_pct,
    })

# ─── BECOME A SELLER (customer → seller upgrade) ─────────────────────────────
@login_required
def become_seller(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if profile.role == 'seller':
        messages.info(request, "You're already a seller — you can post vehicles anytime!")
        if profile.can_post_vehicles():
            return redirect('post_vehicle')
        return redirect('my_profile' if profile.id_verification_status == 'pending' else 'verify_identity')

    if request.method == 'POST':
        profile.role = 'seller'
        profile.save()
        if profile.is_id_exempt():
            messages.success(request, "You're now a seller! Superusers are exempt from ID verification.")
            return redirect('post_vehicle')
        messages.success(
            request,
            "You're now a seller! One last step — verify your identity with a "
            "government ID before you can post your first vehicle."
        )
        return redirect('verify_identity')

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
    pending_ids = UserProfile.objects.filter(
        role='seller', id_verification_status='pending'
    ).exclude(user__is_superuser=True).select_related('user').order_by('id_submitted_at')

    return render(request, 'core/admin_dashboard.html', {
        'pending_ids': pending_ids,
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


# ─── ADMIN: VIEW A SELLER'S SUBMITTED ID (secure, time-limited link) ─────────
@login_required
@user_passes_test(is_admin)
def admin_view_seller_id(request, user_id):
    """
    Generates a short-lived signed URL into the private Supabase bucket so
    staff can review a seller's submitted ID. The link expires in 5 minutes
    and is never stored or shown to anyone else.
    """
    target_user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if not profile.id_document_path:
        messages.error(request, "This user hasn't submitted an ID.")
        return redirect('admin_users')

    url = get_signed_id_url(profile.id_document_path, expires_in=300)
    if not url:
        messages.error(request, "Couldn't generate a secure link to view this ID right now.")
        return redirect('admin_users')

    return redirect(url)


# ─── ADMIN: APPROVE / REJECT A SELLER'S ID ───────────────────────────────────
@login_required
@user_passes_test(is_admin)
@require_POST
def admin_approve_seller_id(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)

    if not profile.id_document_path:
        messages.error(request, "This user hasn't submitted an ID.")
        return redirect('admin_dashboard')

    profile.id_verification_status = 'verified'
    profile.id_reviewed_at = timezone.now()
    profile.id_rejection_reason = ''
    profile.save()

    Notification.objects.create(
        recipient=target_user,
        notif_type='system',
        title='Identity verified',
        message='Your ID has been verified. You can now post vehicle listings on AutoHub.',
    )
    messages.success(request, f"@{target_user.username}'s ID was approved.")
    return redirect('admin_dashboard')


@login_required
@user_passes_test(is_admin)
@require_POST
def admin_reject_seller_id(request, user_id):
    target_user = get_object_or_404(User, pk=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=target_user)
    reason = (request.POST.get('reason') or '').strip()

    if not reason:
        messages.error(request, "Please give a reason so the seller knows what to fix.")
        return redirect('admin_dashboard')

    profile.id_verification_status = 'rejected'
    profile.id_reviewed_at = timezone.now()
    profile.id_rejection_reason = reason
    profile.save()

    Notification.objects.create(
        recipient=target_user,
        notif_type='system',
        title='Identity verification rejected',
        message=f'Your ID could not be verified: {reason} Please upload a new one to try again.',
    )
    messages.success(request, f"@{target_user.username}'s ID was rejected.")
    return redirect('admin_dashboard')