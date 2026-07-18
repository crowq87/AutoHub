from .models import Notification


def notifications_processor(request):
    if request.user.is_authenticated:
        unread_count = Notification.objects.filter(recipient=request.user, is_read=False).count()
        return {'unread_notifications': unread_count}
    return {'unread_notifications': 0}
