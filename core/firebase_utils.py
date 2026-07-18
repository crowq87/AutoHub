import requests
from django.conf import settings

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