from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from firebase_admin import auth as firebase_auth
from .models import UserProfile, VehicleListing, VehiclePhoto, ContactInquiry


class SignUpForm(UserCreationForm):
    first_name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'placeholder': 'First Name'}))
    last_name = forms.CharField(max_length=100, required=True, widget=forms.TextInput(attrs={'placeholder': 'Last Name'}))
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'placeholder': 'Email Address'}))
    phone_number = forms.CharField(max_length=20, required=True, widget=forms.TextInput(attrs={'placeholder': 'e.g. 09171234567'}))
    profile_picture = forms.ImageField(required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email', 'phone_number', 'profile_picture', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            'username': 'Choose a username',
            'password1': 'Create a password',
            'password2': 'Confirm your password',
        }
        for field, placeholder in placeholders.items():
            self.fields[field].widget.attrs['placeholder'] = placeholder
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form-control'

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        firebase_uid = None
        if commit:
            # 1. Create the user in Firebase Auth first
            try:
                fb_user = firebase_auth.create_user(
                    email=user.email,
                    password=self.cleaned_data['password1'],
                    display_name=f"{user.first_name} {user.last_name}",
                )
                firebase_uid = fb_user.uid
            except Exception as e:
                # Don't block signup if Firebase is unreachable —
                # log it so you can reconcile later.
                print(f"[Firebase] failed to create user for {user.email}: {e}")

            user.save()
            UserProfile.objects.create(
                user=user,
                firebase_uid=firebase_uid,
                first_name=self.cleaned_data['first_name'],
                last_name=self.cleaned_data['last_name'],
                phone_number=self.cleaned_data['phone_number'],
                profile_picture=self.cleaned_data.get('profile_picture'),
            )
        return user


class ProfileEditForm(forms.ModelForm):
    email = forms.EmailField(required=True)

    class Meta:
        model = UserProfile
        fields = ['first_name', 'last_name', 'phone_number', 'profile_picture', 'bio']
        widgets = {'bio': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields:
            self.fields[field].widget.attrs['class'] = 'form-control'
        if self.instance and self.instance.user:
            self.fields['email'].initial = self.instance.user.email


class VehicleListingForm(forms.ModelForm):
    class Meta:
        model = VehicleListing
        fields = [
            # Core
            'listing_type', 'brand', 'model', 'year', 'color', 'body_type', 'condition',
            # Engine
            'fuel_type', 'transmission', 'drive_type', 'engine_size', 'horsepower', 'mileage',
            # Body
            'num_seats', 'num_doors',
            # Comfort & Safety
            'has_ac', 'has_dashcam', 'has_power_steering', 'has_power_windows',
            'has_abs', 'has_airbags', 'has_sunroof', 'has_tinted',
            'has_leather_seats', 'has_backup_camera', 'has_gps', 'has_bluetooth',
            'has_spare_tire', 'has_alarm',
            # Documents
            'is_registered', 'has_insurance', 'plate_number',
            # Pricing & Location
            'price', 'price_unit', 'description', 'pickup_location', 'delivery_available',
        ]
        widgets = {
            'description':      forms.Textarea(attrs={'rows': 4, 'placeholder': 'Describe the vehicle condition, features, history, etc.'}),
            'pickup_location':  forms.TextInput(attrs={'placeholder': 'e.g. Pinamungajan Public Market, Toledo City Hall'}),
            'year':             forms.NumberInput(attrs={'min': 1970, 'max': 2025, 'placeholder': 'e.g. 2020'}),
            'mileage':          forms.NumberInput(attrs={'placeholder': 'Mileage in km (optional)'}),
            'price':            forms.NumberInput(attrs={'placeholder': '0.00'}),
            'price_unit':       forms.TextInput(attrs={'placeholder': 'e.g. /day, /month, total'}),
            'engine_size':      forms.TextInput(attrs={'placeholder': 'e.g. 1.5L, 2.0L'}),
            'horsepower':       forms.NumberInput(attrs={'placeholder': 'e.g. 150'}),
            'plate_number':     forms.TextInput(attrs={'placeholder': 'e.g. ABC 1234 (optional)'}),
            'color':            forms.TextInput(attrs={'placeholder': 'e.g. Pearl White, Midnight Black'}),
            'model':            forms.TextInput(attrs={'placeholder': 'e.g. Vios, Civic, Montero'}),
            'brand': forms.TextInput(attrs={'placeholder': 'e.g. Toyota, Honda, Ford, Suzuki...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        checkbox_fields = [
            'has_ac', 'has_dashcam', 'has_power_steering', 'has_power_windows',
            'has_abs', 'has_airbags', 'has_sunroof', 'has_tinted',
            'has_leather_seats', 'has_backup_camera', 'has_gps', 'has_bluetooth',
            'has_spare_tire', 'has_alarm', 'is_registered', 'has_insurance', 'delivery_available',
        ]
        for field in self.fields:
            if field in checkbox_fields:
                self.fields[field].widget.attrs['class'] = 'form-check-input'
            else:
                self.fields[field].widget.attrs['class'] = 'form-control'


class VehiclePhotoForm(forms.ModelForm):
    class Meta:
        model = VehiclePhoto
        fields = ['image']


class ContactInquiryForm(forms.ModelForm):
    class Meta:
        model = ContactInquiry
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': 'Write your message to the seller/owner...',
                'class': 'form-control'
            })
        }


class SearchFilterForm(forms.Form):
    LISTING_TYPE_CHOICES = [('', 'All Types'), ('sale', 'For Sale'), ('rent', 'For Rent')]
    FUEL_CHOICES = [('', 'All Fuel'), ('gasoline', 'Gasoline'), ('diesel', 'Diesel'), ('electric', 'Electric'), ('hybrid', 'Hybrid'), ('lpg', 'LPG')]
    BRAND_CHOICES = [
        ('', 'All Brands'), ('Toyota', 'Toyota'), ('Honda', 'Honda'), ('Mitsubishi', 'Mitsubishi'),
        ('Suzuki', 'Suzuki'), ('Ford', 'Ford'), ('Nissan', 'Nissan'), ('Hyundai', 'Hyundai'),
        ('Kia', 'Kia'), ('Isuzu', 'Isuzu'), ('Chevrolet', 'Chevrolet'), ('Mazda', 'Mazda'),
        ('BMW', 'BMW'), ('Mercedes-Benz', 'Mercedes-Benz'), ('Volkswagen', 'Volkswagen'),
        ('Subaru', 'Subaru'), ('Lexus', 'Lexus'), ('Other', 'Other'),
    ]

    q            = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'Search vehicles...', 'class': 'form-control'}))
    listing_type = forms.ChoiceField(choices=LISTING_TYPE_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    brand = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': 'e.g. Toyota, Honda...', 'class': 'form-control'}))
    fuel_type    = forms.ChoiceField(choices=FUEL_CHOICES, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    min_price    = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={'placeholder': 'Min Price', 'class': 'form-control'}))
    max_price    = forms.DecimalField(required=False, widget=forms.NumberInput(attrs={'placeholder': 'Max Price', 'class': 'form-control'}))