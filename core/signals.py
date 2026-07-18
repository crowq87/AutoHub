from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import VehicleListing, Notification, UserProfile


@receiver(post_save, sender=VehicleListing)
def notify_on_new_listing(sender, instance, created, **kwargs):
    if created:
        # Notify all users about new listing (optional: only notify followers)
        # For now, just a system notification to owner
        Notification.objects.create(
            recipient=instance.owner,
            notif_type='system',
            title='Your listing is live!',
            message=f'Your {instance.year} {instance.brand} {instance.model} has been posted successfully.',
            related_listing=instance,
        )
