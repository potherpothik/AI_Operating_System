import os
import time

import jwt

from identity import keys

# Real issuer — must match what a verifier checks `iss` against
# (services/governance/governance/security/oidc.py's own IDENTITY_URL).
ISSUER = os.environ.get("IDENTITY_ISSUER", "http://localhost:8011")
ACCESS_TOKEN_TTL_SECONDS = 3600


def issue_id_token(user: dict, client_id: str) -> str:
    """A real RS256-signed JWT — real claims, real expiry, signed with the
    real persisted RSA private key. Doubles as this system's access token
    too (no separate opaque-token introspection endpoint): every consumer
    already verifies by signature against the real JWKS, so a second
    token format would add complexity without adding any real guarantee."""
    now = int(time.time())
    claims = {
        "iss": ISSUER,
        "sub": user["sub"],
        "aud": client_id,
        "iat": now,
        "exp": now + ACCESS_TOKEN_TTL_SECONDS,
        "email": user["email"],
        "role": user["role"],
        "preferred_username": user["username"],
    }
    private_key = keys.load_private_key()
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": keys.key_id()})
