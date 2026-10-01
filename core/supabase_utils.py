import time
import requests
from django.conf import settings


def _object_url(path):
    return f"{settings.SUPABASE_URL}/storage/v1/object/{settings.SUPABASE_ID_BUCKET}/{path}"


def _auth_headers(content_type=None):
    headers = {
        'Authorization': f'Bearer {settings.SUPABASE_SERVICE_ROLE_KEY}',
        'apikey': settings.SUPABASE_SERVICE_ROLE_KEY,
    }
    if content_type:
        headers['Content-Type'] = content_type
    return headers


def upload_id_document(user_id, doc_type, uploaded_file):
    """
    Uploads a seller's ID document to a PRIVATE Supabase Storage bucket
    (never Cloudinary, never a public Django media URL). Only the resulting
    storage path is returned for the caller to save on the UserProfile —
    the bucket itself should be configured as private in Supabase, so the
    file is unreachable without a signed URL generated server-side.

    Returns the storage path on success, or None on failure. Never raises —
    callers should treat None as "upload failed, show the user an error".
    """
    original_name = getattr(uploaded_file, 'name', '') or ''
    ext = original_name.rsplit('.', 1)[-1].lower() if '.' in original_name else 'bin'
    if ext not in ('jpg', 'jpeg', 'png', 'webp', 'pdf'):
        ext = 'bin'

    path = f"user_{user_id}/{doc_type}_{int(time.time())}.{ext}"

    try:
        resp = requests.post(
            _object_url(path),
            headers=_auth_headers(
                content_type=getattr(uploaded_file, 'content_type', None)
                or 'application/octet-stream'
            ),
            data=uploaded_file.read(),
            timeout=20,
        )
    except requests.RequestException as e:
        print(f"[Supabase Storage] upload failed for user {user_id}: {e}")
        return None

    if resp.status_code in (200, 201):
        return path

    print(
        f"[Supabase Storage] upload rejected ({resp.status_code}) "
        f"for user {user_id}: {resp.text}"
    )
    return None


def get_signed_id_url(path, expires_in=300):
    """
    Generates a short-lived signed URL (default 5 minutes) so an authorized
    admin can view a seller's uploaded ID without the bucket ever being
    public. Returns None on failure or if no path is given.
    """
    if not path:
        return None

    try:
        resp = requests.post(
            f"{settings.SUPABASE_URL}/storage/v1/object/sign/"
            f"{settings.SUPABASE_ID_BUCKET}/{path}",
            headers=_auth_headers(content_type='application/json'),
            json={'expiresIn': expires_in},
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[Supabase Storage] signed URL request failed for {path}: {e}")
        return None

    if resp.status_code == 200:
        signed_path = resp.json().get('signedURL')
        if signed_path:
            return f"{settings.SUPABASE_URL}/storage/v1{signed_path}"

    print(
        f"[Supabase Storage] signed URL rejected ({resp.status_code}) "
        f"for {path}: {resp.text}"
    )
    return None


def delete_id_document(path):
    """
    Best-effort delete of a previous ID document when a seller re-submits a
    new one. Never raises — failures here shouldn't block the new upload.
    """
    if not path:
        return
    try:
        requests.delete(
            _object_url(path),
            headers=_auth_headers(),
            timeout=10,
        )
    except requests.RequestException as e:
        print(f"[Supabase Storage] delete failed for {path}: {e}")