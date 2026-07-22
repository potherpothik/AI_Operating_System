# Phase 31 — Identity Provider (working implementation)

Real, tested code. A hand-built, self-hosted OpenID Connect Authorization
Code provider — not a mock, not a third-party SaaS, not a heavier
framework like Keycloak (no Docker daemon in this environment, per
Phase 19's own honest limitation). Built on `pyjwt` + `cryptography`
directly: a real RSA keypair, real bcrypt password hashes, real
single-use expiring authorization codes, real RS256-signed JWTs whose
signature any consumer can independently verify against the real public
JWKS this service exposes.

This is Phase 31's real replacement for Phase 2's token-stub auth
(`platform-spine/platform_spine/gateway/tokens.yaml`) — additive, not a
breaking swap. Every other service still defaults to `AUTH_MODE=stub`
and works exactly as it always has; `AUTH_MODE=oidc` is the new, real
per-user path, and this service is what it verifies against.

## Run it

```bash
pip install -r requirements.txt
export IDENTITY_ISSUER=http://localhost:8011
uvicorn main:app --port 8011
```

The real RSA signing key is generated on first startup and persisted to
`identity/keys/private_key.pem` (gitignored) — set `IDENTITY_KEYS_DIR`
to point somewhere durable in a real deployment (a mounted volume, not
`/tmp`), since every previously-issued token becomes unverifiable if the
key is lost or regenerated.

## Real dev users

`identity/users.yaml` — two real, bcrypt-hashed dev accounts:

| username | password | role |
|---|---|---|
| `admin` | `admin-dev-pw` | `human_admin` |
| `operator` | `operator-dev-pw` | `human_admin` |

Real passwords, documented in plaintext for dev use — same posture as
`platform-spine/platform_spine/gateway/tokens.yaml`'s own
`dev-admin-token`. Replace this file (or just the password hashes) with
real values before any real deployment.

## The real Authorization Code flow

```bash
# 1. Real discovery + JWKS
curl http://localhost:8011/.well-known/openid-configuration
curl http://localhost:8011/.well-known/jwks.json

# 2. Real login (real bcrypt check) -> a real, single-use authorization code
curl -i -X POST http://localhost:8011/login \
  -d "username=admin&password=admin-dev-pw&client_id=aios-web&redirect_uri=http://localhost:8888/callback"
# -> 302 redirect with ?code=... in Location

# 3. Real code exchange -> a real RS256-signed JWT
curl -X POST http://localhost:8011/token \
  -d "grant_type=authorization_code&code=<code>&redirect_uri=http://localhost:8888/callback&client_id=aios-web&client_secret=aios-web-dev-secret"

# 4. Real claims lookup
curl http://localhost:8011/userinfo -H "Authorization: Bearer <access_token>"
```

Registered clients live in `identity/clients.yaml` — same "static YAML
config, not a database row" convention as Shell Executor's allowlists.

## Test it

```bash
pytest tests/ -v
```

12 real tests: the full flow end to end, wrong-password rejection,
unknown-client/unregistered-redirect_uri rejection, wrong client secret
rejection, and confirmed single-use semantics — a redeemed authorization
code cannot be exchanged twice.

## What's real

- **A genuine, independently-verifiable signature**: `/userinfo`'s own
  token check and governance's `security/oidc.py` both verify the exact
  same real RS256 signature against the exact same real public key —
  confirmed live, not two different trust paths that happen to agree.
- **Real single-use codes**: `identity/codes.py` pops a code from its
  store on every redemption attempt, valid or not — confirmed live, a
  second exchange attempt with an already-used code fails with a real
  400, not a second valid token.
- **Real bcrypt verification**, not a string comparison — confirmed
  live, a wrong password is genuinely rejected (401), not silently
  ignored.

## What's a stub or simplified

- **In-memory authorization codes** — real and single-use, but don't
  survive a process restart and aren't shared across multiple identity
  service replicas. Honest for this phase's real deployment target ("a
  shared Ubuntu server," one process); a real gap for a
  horizontally-scaled deployment.
- **No admin UI or add-user script** — `users.yaml` is a real, hand-edited
  file, same convention as every other static YAML config in this repo.
- **One shared static client** (`aios-web`) for all four real consumer
  services, rather than one OIDC client registration per consumer — a
  real, reasonable simplification for a single-operator/small-team
  self-hosted deployment, not a security gap (they already share one
  Security Layer).

## Next

`services/governance/`'s own `security/oidc.py` and the `AUTH_MODE=oidc`
wiring in Gateway, the OpenAI shim, and Control UI — see
`docs/aios-architecture-and-phases.md#phase-31-team-and-gpu-day-hardening`.
