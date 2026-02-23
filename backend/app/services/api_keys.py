import hashlib
import secrets
from uuid import uuid4


API_KEY_PREFIX = "dlk_"


def issue_api_key() -> tuple[str, str, str, str]:
    secret = secrets.token_urlsafe(30)
    raw_key = f"{API_KEY_PREFIX}{secret}"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    key_prefix = raw_key[: min(12, len(raw_key))]
    key_last4 = raw_key[-4:]
    return raw_key, key_hash, key_prefix, key_last4


def new_api_key_id():
    return uuid4()
