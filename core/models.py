from django.db import models
from django.contrib.auth.models import User
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models import Avg


class UserProfile(models.Model):
    ROLE_CHOICES = [
        ('customer', 'Customer (Buy / Rent)'),
        ('seller', 'Seller / Lister'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='customer')
    firebase_uid = models.CharField(max_length=128, unique=True, blank=True, null=True)

    # Default True so existing accounts (created before this field existed) keep
    # working without interruption. New signups explicitly set this to False in
    # SignUpForm.save(), so only freshly created accounts must verify.
    email_verified = models.BooleanField(default=True, verbose_name='Email Verified')

    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    profile_picture = models.ImageField(upload_to='profile_pics/', blank=True, null=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ── Seller identity verification ──
    # The actual ID file is NEVER stored in Django/Cloudinary — it lives in a
    # private Supabase Storage bucket, and only its storage path is kept
    # here. Access to the real file requires a short-lived signed URL
    # generated server-side (see core/supabase_utils.py), so it is never
    # publicly reachable.
    ID_DOC_TYPE_CHOICES = [
        ('drivers_license', "Driver's License"),
        ('national_id', 'National ID (PhilSys)'),
        ('other_gov_id', 'Other Government-Issued ID'),
    ]

    ID_VERIFICATION_CHOICES = [
        ('not_submitted', 'Not Submitted'),
        ('pending', 'Pending Admin Review'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    id_document_type = models.CharField(
        max_length=20, choices=ID_DOC_TYPE_CHOICES, blank=True
    )
    id_document_path = models.CharField(
        max_length=255,
        blank=True,
        help_text='Storage path/key inside the private Supabase bucket. Never a public URL.',
    )
    id_verification_status = models.CharField(
        max_length=20, choices=ID_VERIFICATION_CHOICES, default='not_submitted'
    )
    id_submitted_at = models.DateTimeField(null=True, blank=True)
    id_reviewed_at = models.DateTimeField(null=True, blank=True)
    id_rejection_reason = models.TextField(blank=True)

    # ── Account ban (set by admins from the Manage Users page) ──
    # A banned account cannot log in and its listings are hidden until it is
    # reinstated. The reason is shown to the user when they try to sign in.
    is_banned = models.BooleanField(default=False)
    banned_at = models.DateTimeField(null=True, blank=True)
    ban_reason = models.TextField(blank=True)

    def get_full_name(self):
        """First + last name for display. Prefers the profile's own names and
        falls back to the linked User's names. Returns '' if neither is set,
        so templates can use |default:user.username."""
        first = (self.first_name or self.user.first_name or '').strip()
        last = (self.last_name or self.user.last_name or '').strip()
        return f"{first} {last}".strip()

    def has_submitted_id(self):
        """True once an ID has been uploaded (awaiting review or already
        verified). Submission alone does NOT unlock posting — see
        can_post_vehicles()."""
        return self.id_verification_status in ('pending', 'verified')

    def is_id_verified(self):
        """True only after an admin has reviewed and approved the ID."""
        return self.id_verification_status == 'verified'

    def is_id_exempt(self):
        """Admins (staff and superusers) bypass ID verification entirely."""
        return self.user.is_superuser or self.user.is_staff

    def is_verified_account(self):
        """What the green check badge means: an admin, or a seller whose ID
        an admin has approved."""
        return self.is_id_exempt() or self.is_id_verified()

    def can_post_vehicles(self):
        """Sellers may post only once an admin has verified their ID.
        Superusers are exempt from ID verification."""
        if self.role != 'seller':
            return False
        return self.is_id_exempt() or self.is_id_verified()

    def average_rating(self):
        """Average of all ratings this user has received as a seller/renter, or None if unrated."""
        result = self.user.received_ratings.aggregate(avg=Avg('score'))['avg']
        return round(result, 1) if result is not None else None

    def rating_count(self):
        return self.user.received_ratings.count()


class VehicleListing(models.Model):
    LISTING_TYPE_CHOICES = [
        ('sale', 'For Sale'),
        ('rent', 'For Rent'),
    ]
    FUEL_TYPE_CHOICES = [
        ('gasoline', 'Gasoline'),
        ('diesel', 'Diesel'),
        ('electric', 'Electric'),
        ('hybrid', 'Hybrid'),
        ('lpg', 'LPG'),
    ]
    TRANSMISSION_CHOICES = [
        ('automatic', 'Automatic'),
        ('manual', 'Manual'),
        ('cvt', 'CVT'),
    ]
    BRAND_CHOICES = [
        ('Toyota', 'Toyota'),
        ('Honda', 'Honda'),
        ('Mitsubishi', 'Mitsubishi'),
        ('Suzuki', 'Suzuki'),
        ('Ford', 'Ford'),
        ('Nissan', 'Nissan'),
        ('Hyundai', 'Hyundai'),
        ('Kia', 'Kia'),
        ('Isuzu', 'Isuzu'),
        ('Chevrolet', 'Chevrolet'),
        ('Mazda', 'Mazda'),
        ('BMW', 'BMW'),
        ('Mercedes-Benz', 'Mercedes-Benz'),
        ('Volkswagen', 'Volkswagen'),
        ('Subaru', 'Subaru'),
        ('Lexus', 'Lexus'),
        ('Other', 'Other'),
    ]
    BODY_TYPE_CHOICES = [
        ('sedan', 'Sedan'),
        ('suv', 'SUV / Crossover'),
        ('pickup', 'Pickup Truck'),
        ('van', 'Van / Minivan'),
        ('hatchback', 'Hatchback'),
        ('coupe', 'Coupe'),
        ('wagon', 'Station Wagon'),
        ('motorcycle', 'Motorcycle'),
        ('truck', 'Truck'),
        ('other', 'Other'),
    ]
    DRIVE_TYPE_CHOICES = [
        ('fwd', 'Front-Wheel Drive (FWD)'),
        ('rwd', 'Rear-Wheel Drive (RWD)'),
        ('awd', 'All-Wheel Drive (AWD)'),
        ('4wd', '4-Wheel Drive (4WD)'),
    ]
    CONDITION_CHOICES = [
        ('brand_new', 'Brand New'),
        ('like_new', 'Like New'),
        ('good', 'Good'),
        ('fair', 'Fair'),
        ('for_parts', 'For Parts'),
    ]
    SEATS_CHOICES = [(str(i), str(i)) for i in range(2, 13)]
    DOORS_CHOICES = [('2', '2'), ('3', '3'), ('4', '4'), ('5', '5')]

    # ── Core Info ──
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='listings')
    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE_CHOICES)
    brand = models.CharField(max_length=100)
    model = models.CharField(max_length=100)
    year = models.IntegerField()
    color = models.CharField(max_length=50)
    body_type = models.CharField(max_length=20, choices=BODY_TYPE_CHOICES, default='sedan')
    condition = models.CharField(max_length=20, choices=CONDITION_CHOICES, default='good')

    # ── Engine & Performance ──
    fuel_type = models.CharField(max_length=20, choices=FUEL_TYPE_CHOICES)
    transmission = models.CharField(max_length=20, choices=TRANSMISSION_CHOICES)
    drive_type = models.CharField(max_length=10, choices=DRIVE_TYPE_CHOICES, blank=True)
    engine_size = models.CharField(max_length=20, blank=True, help_text='e.g. 1.5L, 2.0L')
    horsepower = models.IntegerField(blank=True, null=True, help_text='in hp')
    mileage = models.IntegerField(blank=True, null=True, help_text='in km')

    # ── Body ──
    num_seats = models.CharField(max_length=5, choices=SEATS_CHOICES, default='5')
    num_doors = models.CharField(max_length=5, choices=DOORS_CHOICES, default='4')

    # ── Comfort & Safety Features ──
    has_ac = models.BooleanField(default=False, verbose_name='Air Conditioning')
    has_dashcam = models.BooleanField(default=False, verbose_name='Dashcam')
    has_power_steering = models.BooleanField(default=False, verbose_name='Power Steering')
    has_power_windows = models.BooleanField(default=False, verbose_name='Power Windows')
    has_abs = models.BooleanField(default=False, verbose_name='ABS Brakes')
    has_airbags = models.BooleanField(default=False, verbose_name='Airbags')
    has_sunroof = models.BooleanField(default=False, verbose_name='Sunroof / Moonroof')
    has_tinted = models.BooleanField(default=False, verbose_name='Tinted Windows')
    has_leather_seats = models.BooleanField(default=False, verbose_name='Leather Seats')
    has_backup_camera = models.BooleanField(default=False, verbose_name='Backup Camera')
    has_gps = models.BooleanField(default=False, verbose_name='GPS Navigation')
    has_bluetooth = models.BooleanField(default=False, verbose_name='Bluetooth / Audio')
    has_spare_tire = models.BooleanField(default=False, verbose_name='Spare Tire')
    has_alarm = models.BooleanField(default=False, verbose_name='Car Alarm / Immobilizer')

    # ── Documents ──
    is_registered = models.BooleanField(default=False, verbose_name='Registered (OR/CR Complete)')
    has_insurance = models.BooleanField(default=False, verbose_name='With Insurance')
    plate_number = models.CharField(max_length=20, blank=True, help_text='Optional')

    # Photo/scan of the OR/CR. Stored in the PRIVATE Supabase bucket (same one
    # used for seller IDs) — only the storage path lives here, and only admins
    # can open it through a short-lived signed link.
    or_cr_document_path = models.CharField(max_length=255, blank=True)
    # Set by an admin after checking the uploaded document. Drives the public
    # "OR/CR verified" badge.
    or_cr_verified = models.BooleanField(default=False)

    # ── Vehicle History ──
    PREVIOUS_OWNER_CHOICES = [
        ('1', '1 Owner'),
        ('2', '2 Owners'),
        ('3', '3 Owners'),
        ('4+', '4+ Owners'),
        ('unknown', 'Unknown'),
    ]

    HISTORY_CHOICES = [
        ('no', 'No'),
        ('yes', 'Yes'),
        ('unknown', 'Not Sure'),
    ]

    MODIFICATION_CHOICES = [
        ('stock', 'Stock / Original'),
        ('modified', 'Modified'),
    ]

    SERVICE_RECORD_CHOICES = [
        ('available', 'Available'),
        ('not_available', 'Not Available'),
    ]

    previous_owners = models.CharField(
        max_length=10,
        choices=PREVIOUS_OWNER_CHOICES,
        default='unknown',
        blank=True
    )

    accident_history = models.CharField(
        max_length=10,
        choices=HISTORY_CHOICES,
        default='no',
        blank=True
    )

    flood_damage = models.CharField(
        max_length=10,
        choices=HISTORY_CHOICES,
        default='no',
        blank=True
    )

    modification_status = models.CharField(
        max_length=10,
        choices=MODIFICATION_CHOICES,
        default='stock',
        blank=True
    )

    service_records = models.CharField(
        max_length=20,
        choices=SERVICE_RECORD_CHOICES,
        default='not_available',
        blank=True
    )

    reason_for_selling = models.CharField(
        max_length=255,
        blank=True
    )

    # ── Pricing & Location ──
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_unit = models.CharField(max_length=20, default='total', help_text='e.g. /day, /month, total')

    price_negotiable = models.BooleanField(
        default=False,
        verbose_name='Price Negotiable'
    )

    description = models.TextField()
    pickup_location = models.CharField(max_length=255)
    delivery_available = models.BooleanField(default=False)

    

    # ── Availability status ──
    AVAILABILITY_CHOICES = [
        ('available', 'Available'),
        ('rented', 'Currently Rented'),
        ('sold', 'Sold'),
    ]
    availability_status = models.CharField(
        max_length=20,
        choices=AVAILABILITY_CHOICES,
        default='available',
        help_text='Lets buyers/renters know at a glance if this vehicle is still available.',
    )

    # ── Status ──
    is_active = models.BooleanField(default=True)
    # New listings must be reviewed by an admin before they appear publicly.
    is_approved = models.BooleanField(default=False)
    # True when this listing was switched off automatically because its owner
    # was banned, so it can be switched back on if the owner is reinstated.
    hidden_by_ban = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.year} {self.brand} {self.model} - {self.get_listing_type_display()}"

    def get_main_photo(self):
        photo = self.photos.first()
        return photo.image.url if photo else None

    def average_rating(self):
        """Average of the rental-experience ratings left on this specific vehicle listing."""
        result = self.vehicle_ratings.aggregate(avg=Avg('score'))['avg']
        return round(result, 1) if result is not None else None

    def rating_count(self):
        return self.vehicle_ratings.count()

    def is_available(self):
        return self.availability_status == 'available'

    def status_badge_css(self):
        """CSS color tag used by templates for the status badge."""
        return {
            'available': 'success',
            'rented': 'warning',
            'sold': 'danger',
        }.get(self.availability_status, 'secondary')

    class Meta:
        ordering = ['-created_at']


class VehiclePhoto(models.Model):
    listing = models.ForeignKey(VehicleListing, on_delete=models.CASCADE, related_name='photos')
    image = models.ImageField(upload_to='vehicle_photos/')
    is_main = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Photo for {self.listing}"


class Notification(models.Model):
    NOTIF_TYPE_CHOICES = [
        ('new_listing', 'New Listing'),
        ('message', 'Message'),
        ('update', 'Post Update'),
        ('system', 'System'),
    ]
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    notif_type = models.CharField(max_length=20, choices=NOTIF_TYPE_CHOICES, default='system')
    title = models.CharField(max_length=200)
    message = models.TextField()
    related_listing = models.ForeignKey(VehicleListing, on_delete=models.SET_NULL, null=True, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Notif for {self.recipient.username}: {self.title}"


class ContactInquiry(models.Model):
    listing = models.ForeignKey(VehicleListing, on_delete=models.CASCADE, related_name='inquiries')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_inquiries')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Inquiry from {self.sender.username} on {self.listing}"
    
class ChatConversation(models.Model):
    """
    One private conversation between one customer and one vehicle seller
    about one specific vehicle listing.
    """

    listing = models.ForeignKey(
        VehicleListing,
        on_delete=models.CASCADE,
        related_name='chat_conversations'
    )

    customer = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='vehicle_chat_conversations'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        constraints = [
            models.UniqueConstraint(
                fields=['listing', 'customer'],
                name='unique_customer_vehicle_conversation'
            )
        ]

    @property
    def seller(self):
        return self.listing.owner

    def __str__(self):
        return (
            f"Chat: {self.customer.username} → "
            f"{self.listing.owner.username} - {self.listing}"
        )


class ChatMessage(models.Model):
    """
    Individual messages inside a vehicle/customer conversation.
    """

    conversation = models.ForeignKey(
        ChatConversation,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    sender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='sent_vehicle_chat_messages'
    )

    message = models.TextField()

    is_read = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return (
            f"Message from {self.sender.username} "
            f"in conversation {self.conversation.id}"
        )


class SellerRating(models.Model):
    """
    A trust rating left by a customer for a seller/renter's ACCOUNT, based on
    their overall experience dealing with that person (communication,
    honesty, reliability, etc). One rating per (seller, rater) pair — the
    rater can update their existing rating instead of leaving a new one.
    """

    seller = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='received_ratings',
    )

    rater = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='given_seller_ratings',
    )

    # Optional context: which listing prompted this rating. Kept even if the
    # listing itself is later removed, so the review text still makes sense.
    listing = models.ForeignKey(
        VehicleListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='seller_ratings_from_this_listing',
    )

    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1 (poor) to 5 (excellent)',
    )
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['seller', 'rater'],
                name='unique_seller_rating_per_rater',
            )
        ]

    def __str__(self):
        return f"{self.rater.username} rated {self.seller.username}: {self.score}/5"


class VehicleRating(models.Model):
    """
    A rating left by a renter/buyer for a specific vehicle LISTING, based on
    their experience with that particular vehicle (condition, accuracy of
    the listing, how the rental went, etc). One rating per (listing, rater)
    pair — the rater can update their existing rating.
    """

    listing = models.ForeignKey(
        VehicleListing,
        on_delete=models.CASCADE,
        related_name='vehicle_ratings',
    )

    rater = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='given_vehicle_ratings',
    )

    score = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text='1 (poor) to 5 (excellent)',
    )
    comment = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['listing', 'rater'],
                name='unique_vehicle_rating_per_rater',
            )
        ]

    def __str__(self):
        return f"{self.rater.username} rated {self.listing}: {self.score}/5"