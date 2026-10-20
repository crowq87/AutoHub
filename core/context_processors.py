from django.db.models import Q

from .models import Notification, ChatMessage


def notifications_processor(request):
    if not request.user.is_authenticated:
        return {
            'unread_notifications': 0,
            'recent_notifications': [],
            'show_chat_widget': False,
            'unread_chat_total': 0,
        }

    user = request.user
    qs = Notification.objects.filter(recipient=user)

    # The global chat bubble appears on every page for verified users. Its
    # inbox only lists conversations the user is actually part of.
    profile = getattr(user, 'profile', None)
    show_chat = bool(profile and profile.email_verified)
    unread_chat = 0
    if show_chat:
        unread_chat = ChatMessage.objects.filter(is_read=False).filter(
            Q(conversation__customer=user) | Q(conversation__listing__owner=user)
        ).exclude(sender=user).count()

    return {
        'unread_notifications': qs.filter(is_read=False).count(),
        'recent_notifications': list(
            qs.select_related('related_listing').order_by('-created_at')[:5]
        ),
        'show_chat_widget': show_chat,
        'unread_chat_total': unread_chat,
    }