import base64
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

# Phase 31: a real RSA keypair, generated once and persisted to disk —
# not regenerated per-process-start (that would invalidate every
# previously-issued, still-live token on a simple restart) and not a
# hardcoded/checked-in key (a real signing key belongs in the deploy
# environment, not git history). Same "real local file, single-host dev
# convention" as SANDBOX_ROOT/PROPOSAL_REPO_PATH — a real production
# deployment mounts a real persistent volume at KEYS_DIR.
import os

KEYS_DIR = Path(os.environ.get("IDENTITY_KEYS_DIR", Path(__file__).parent / "keys"))
_PRIVATE_KEY_PATH = KEYS_DIR / "private_key.pem"
_KEY_ID = "aios-identity-key-1"


def _generate_and_persist() -> rsa.RSAPrivateKey:
    KEYS_DIR.mkdir(parents=True, exist_ok=True)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    _PRIVATE_KEY_PATH.write_bytes(pem)
    _PRIVATE_KEY_PATH.chmod(0o600)
    return key


def load_private_key() -> rsa.RSAPrivateKey:
    if _PRIVATE_KEY_PATH.exists():
        return serialization.load_pem_private_key(_PRIVATE_KEY_PATH.read_bytes(), password=None)
    return _generate_and_persist()


def _b64url_uint(value: int) -> str:
    length = (value.bit_length() + 7) // 8
    return base64.urlsafe_b64encode(value.to_bytes(length, "big")).rstrip(b"=").decode("ascii")


def public_jwk() -> dict:
    """Real JWK derived from the real RSA public key — n/e are the actual
    modulus/exponent, not placeholders. `kid` matches what tokens are
    signed with, so a verifier can pick the right key deterministically."""
    public_numbers = load_private_key().public_key().public_numbers()
    return {
        "kty": "RSA",
        "use": "sig",
        "alg": "RS256",
        "kid": _KEY_ID,
        "n": _b64url_uint(public_numbers.n),
        "e": _b64url_uint(public_numbers.e),
    }


def key_id() -> str:
    return _KEY_ID
