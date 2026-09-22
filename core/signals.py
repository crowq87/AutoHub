from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import VehicleListing, Notification, UserProfile


@receiver(post_save, sender=VehicleListing)
def notify_on_new_listing(sender, instance, created, **kwargs):
    if created:
        Notification.objects.create(
            recipient=instance.owner,
            notif_type='system',
            title='Listing submitted for review',
            message=f'Your {instance.year} {instance.brand} {instance.model} has been received and is pending admin approval before it goes live.',
            related_listing=instance,
        )