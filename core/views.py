from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.mail import send_mail
from django.db.models import Q, Count
from django.http import JsonResponse
from firebase_admin import auth as firebase_auth
from .models import VehicleListing, VehiclePhoto, Notification, UserProfile, ContactInquiry
from .forms import SignUpForm, ProfileEditForm, VehicleListingForm, VehiclePhotoForm, ContactInquiryForm, SearchFilterForm
from firebase_admin import auth as firebase_auth
from .firebase_utils import firebase_verify_password
from .models import VehicleListing, VehiclePhoto, Notification, UserProfile, ContactInquiry
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
            user = form.save()
            login(request, user)
            messages.success(request, f"Welcome to AutoHub, {user.first_name}! Your account has been created.")
            return redirect('dashboard')
    else:
        form = SignUpForm()
    return render(request, 'core/signup.html', {'form': form})


# ─── LOGIN ────────────────────────────────────────────────────────────────────
def login_view(request):
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
            firebase_uid = firebase_verify_password(django_user.email, password)
            if firebase_uid:
                django_user.backend = 'django.contrib.auth.backends.ModelBackend'
                login(request, django_user)
                messages.success(request, f"Welcome back, {django_user.first_name or django_user.username}!")
                return redirect('dashboard')

        messages.error(request, "Invalid username or password.")
    else:
        form = AuthenticationForm()
    return render(request, 'core/login.html', {'form': form})


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
    listing = get_object_or_404(VehicleListing, pk=pk, is_active=True)
    inquiry_form = ContactInquiryForm()

    if request.method == 'POST':
        inquiry_form = ContactInquiryForm(request.POST)
        if inquiry_form.is_valid():
            inquiry = inquiry_form.save(commit=False)
            inquiry.listing = listing
            inquiry.sender = request.user
            inquiry.save()
            # Notify the listing owner
            Notification.objects.create(
                recipient=listing.owner,
                notif_type='message',
                title=f"New inquiry on your {listing.brand} {listing.model}",
                message=f"{request.user.username} sent: {inquiry.message[:100]}",
                related_listing=listing,
            )
            messages.success(request, "Your inquiry has been sent!")
            return redirect('vehicle_detail', pk=pk)

    return render(request, 'core/vehicle_detail.html', {
        'listing': listing,
        'inquiry_form': inquiry_form,
    })


# ─── POST / EDIT VEHICLE ──────────────────────────────────────────────────────
@login_required
def post_vehicle(request):
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

            messages.success(request, "Your vehicle has been listed successfully!")
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
            request.user.email = form.cleaned_data['email']
            request.user.save()
            messages.success(request, "Profile updated successfully!")
            return redirect('my_profile')
    else:
        form = ProfileEditForm(instance=profile)

    return render(request, 'core/my_profile.html', {
        'form': form,
        'profile': profile,
        'my_listings': my_listings,
    })



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
def admin_approve_listing(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk)
    listing.is_approved = True
    listing.save()
    messages.success(request, f"Listing '{listing}' approved.")
    return redirect('admin_dashboard')


@login_required
@user_passes_test(is_admin)
def admin_remove_listing(request, pk):
    listing = get_object_or_404(VehicleListing, pk=pk)
    listing.is_active = False
    listing.save()
    messages.success(request, f"Listing '{listing}' removed.")
    return redirect('admin_dashboard')


@login_required
@user_passes_test(is_admin)
def admin_users(request):
    users = User.objects.all().order_by('-date_joined')
    return render(request, 'core/admin_users.html', {'users': users})
