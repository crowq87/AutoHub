from django.db import models
from django.contrib.auth.models import User


class UserProfile(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )

    firebase_uid = models.CharField(
        max_length=128,
        unique=True,
        blank=True,
        null=True
    )

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    phone_number = models.CharField(max_length=20)
    profile_picture = models.ImageField(
        upload_to='profile_pics/',
        blank=True,
        null=True
    )
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

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

    # ── Pricing & Location ──
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_unit = models.CharField(max_length=20, default='total', help_text='e.g. /day, /month, total')
    description = models.TextField()
    pickup_location = models.CharField(max_length=255)
    delivery_available = models.BooleanField(default=False)

    # ── Status ──
    is_active = models.BooleanField(default=True)
    is_approved = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.year} {self.brand} {self.model} - {self.get_listing_type_display()}"

    def get_main_photo(self):
        photo = self.photos.first()
        return photo.image.url if photo else None

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