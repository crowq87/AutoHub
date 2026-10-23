from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


class BannedUserMiddleware:
    """
    Signs out any logged-in user whose account has been banned, so a ban takes
    effect immediately instead of waiting for the session to expire.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, 'user', None)
        if user is not None and user.is_authenticated:
            profile = getattr(user, 'profile', None)
            if profile is not None and profile.is_banned:
                logout(request)
                messages.error(
                    request,
                    "This account has been banned and can no longer be used."
                )
                return redirect('login')
        return self.get_response(request)