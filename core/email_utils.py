import requests
from django.conf import settings
from django.core.mail import send_mail

BREVO_SEND_URL = "https://api.brevo.com/v3/smtp/email"


def _send_via_brevo(subject, body, to_email):
    """
    Sends over HTTPS (port 443) using Brevo's transactional email API.
    Render blocks outbound SMTP ports (25/465/587) on free web services,
    but plain HTTPS requests are never blocked, so this works everywhere.
    """
    payload = {
        "sender": {
            "name": settings.BREVO_SENDER_NAME,
            "email": settings.BREVO_SENDER_EMAIL,
        },
        "to": [{"email": to_email}],
        "subject": subject,
        "textContent": body,
    }
    headers = {
        "api-key": settings.BREVO_API_KEY,
        "accept": "application/json",
        "content-type": "application/json",
    }

    resp = requests.post(BREVO_SEND_URL, json=payload, headers=headers, timeout=15)

    if resp.status_code in (200, 201, 202):
        return True

    print(f"[Email] Brevo rejected the message to {to_email} "
          f"({resp.status_code}): {resp.text}")
    return False


def send_email(subject, body, to_email):
    """
    Sends a plain-text email. Returns True on success, False on failure
    (never raises, so signup / password reset never crash on a mail error).

    - If BREVO_API_KEY is set  -> sends through the Brevo HTTPS API.
    - Otherwise                -> falls back to Django's SMTP settings
                                  (fine for local development).
    """
    try:
        if settings.BREVO_API_KEY:
            return _send_via_brevo(subject, body, to_email)

        print("[Email] BREVO_API_KEY is not set on this server - "
              "falling back to SMTP (blocked on Render's free tier).")
        send_mail(
            subject=subject,
            message=body,
            from_email=None,  # uses DEFAULT_FROM_EMAIL
            recipient_list=[to_email],
        )
        return True

    except Exception as e:
        print(f"[Email] failed to send '{subject}' to {to_email}: {type(e).__name__}: {e}")
        return False