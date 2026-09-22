import requests
from django.conf import settings
from django.core.mail import send_mail
from firebase_admin import auth as firebase_auth
import socket
import urllib3.util.connection as urllib3_cn

def allowed_gai_family():
    return socket.AF_INET  # force IPv4

urllib3_cn.allowed_gai_family = allowed_gai_family
FIREBASE_SIGNIN_URL = (
    "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword"
    "?key={api_key}"
)


def firebase_verify_password(email, password):
    """
    Verifies an email/password pair against Firebase Auth.
    Returns the Firebase localId (uid) if correct, otherwise None.
    """
    url = FIREBASE_SIGNIN_URL.format(api_key=settings.FIREBASE_WEB_API_KEY)
    try:
        resp = requests.post(url, json={
            "email": email,
            "password": password,
            "returnSecureToken": True,
        }, timeout=10)
    except requests.RequestException as e:
        print(f"[Firebase] network error verifying password for {email}: {e}")
        return None

    if resp.status_code == 200:
        return resp.json().get("localId")

    # Non-200 means wrong password / user not found / disabled, etc.
    return None


def send_firebase_verification_email(email):
    """
    Generates a Firebase email-verification link and emails it to the user.
    Returns True if the email was sent, False otherwise (never raises, so
    callers like signup can continue even if the email fails to send).
    """
    try:
        link = firebase_auth.generate_email_verification_link(email)
        send_mail(
            subject="Verify your AutoHub email address",
            message=(
                f"Hi,\n\nPlease confirm your email address to unlock posting, "
                f"buying/renting, and messaging sellers on AutoHub:\n\n{link}\n\n"
                "If you didn't create an AutoHub account, you can safely ignore this email."
            ),
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[email],
        )
        return True
    except Exception as e:
        print(f"[Firebase] verification email failed for {email}: {e}")
        return False


def firebase_is_email_verified(firebase_uid):
    """
    Looks up the live 'email_verified' flag on the Firebase Auth account.
    Returns None if the lookup fails (e.g. no uid, network error) so callers
    can distinguish "not verified" from "couldn't check".
    """
    if not firebase_uid:
        return None
    try:
        fb_user = firebase_auth.get_user(firebase_uid)
        return bool(fb_user.email_verified)
    except Exception as e:
        print(f"[Firebase] email_verified lookup failed for uid {firebase_uid}: {e}")
        return None