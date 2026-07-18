from django.contrib import admin
from .models import UserProfile, VehicleListing, VehiclePhoto, Notification, ContactInquiry


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'first_name', 'last_name', 'phone_number', 'created_at']
    search_fields = ['user__username', 'first_name', 'last_name', 'phone_number']


class VehiclePhotoInline(admin.TabularInline):
    model = VehiclePhoto
    extra = 1


@admin.register(VehicleListing)
class VehicleListingAdmin(admin.ModelAdmin):
    list_display = ['brand', 'model', 'year', 'listing_type', 'price', 'owner', 'is_active', 'is_approved', 'created_at']
    list_filter = ['listing_type', 'brand', 'fuel_type', 'is_active', 'is_approved']
    search_fields = ['brand', 'model', 'owner__username', 'pickup_location']
    inlines = [VehiclePhotoInline]
    actions = ['approve_listings', 'deactivate_listings']

    def approve_listings(self, request, queryset):
        queryset.update(is_approved=True)
    approve_listings.short_description = "Approve selected listings"

    def deactivate_listings(self, request, queryset):
        queryset.update(is_active=False)
    deactivate_listings.short_description = "Deactivate selected listings"


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ['recipient', 'title', 'notif_type', 'is_read', 'created_at']
    list_filter = ['notif_type', 'is_read']


@admin.register(ContactInquiry)
class ContactInquiryAdmin(admin.ModelAdmin):
    list_display = ['sender', 'listing', 'created_at']
    search_fields = ['sender__username', 'listing__brand']
