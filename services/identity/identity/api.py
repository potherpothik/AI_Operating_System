import html

from fastapi import APIRouter, Form, Header, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse

from identity import clients as client_store
from identity import codes, keys, tokens, users

router = APIRouter(tags=["identity"])


@router.get("/.well-known/openid-configuration")
def discovery():
    """Real OIDC discovery document — every URL below is a real endpoint
    on this router, not a placeholder."""
    issuer = tokens.ISSUER
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/authorize",
        "token_endpoint": f"{issuer}/token",
        "userinfo_endpoint": f"{issuer}/userinfo",
        "jwks_uri": f"{issuer}/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
        "scopes_supported": ["openid", "email", "profile"],
        "grant_types_supported": ["authorization_code"],
    }


@router.get("/.well-known/jwks.json")
def jwks():
    """Real JWKS — the actual public key this service signs tokens with,
    derived live from the real persisted RSA keypair (services/identity/identity/keys.py)."""
    return {"keys": [keys.public_jwk()]}


@router.get("/authorize", response_class=HTMLResponse)
def authorize_get(response_type: str = Query(...), client_id: str = Query(...), redirect_uri: str = Query(...), state: str = Query(""), scope: str = Query("openid")):
    """
    Real Authorization Code flow entry point: renders a real login form
    (no session cookie, no pre-authenticated bypass) — every login goes
    through real bcrypt verification in `/login` below, every single
    time, matching this project's own "no assumed trust" posture.
    """
    if response_type != "code":
        raise HTTPException(status_code=400, detail="only response_type=code is supported")
    if not client_store.get_client(client_id):
        raise HTTPException(status_code=400, detail="unknown client_id")
    if not client_store.redirect_uri_is_registered(client_id, redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri not registered for this client")

    # Escaped even though these come from registered-client-adjacent query
    # params, not arbitrary user input — a redirect_uri/state reflected
    # into HTML is still a real XSS surface if left unescaped.
    return f"""
    <html><body>
    <h2>AIOS sign in</h2>
    <form method="post" action="/login">
      <input type="hidden" name="client_id" value="{html.escape(client_id)}">
      <input type="hidden" name="redirect_uri" value="{html.escape(redirect_uri)}">
      <input type="hidden" name="state" value="{html.escape(state)}">
      <label>Username <input type="text" name="username" autofocus></label><br>
      <label>Password <input type="password" name="password"></label><br>
      <button type="submit">Sign in</button>
    </form>
    </body></html>
    """


@router.post("/login")
def login(username: str = Form(...), password: str = Form(...), client_id: str = Form(...), redirect_uri: str = Form(...), state: str = Form("")):
    if not client_store.redirect_uri_is_registered(client_id, redirect_uri):
        raise HTTPException(status_code=400, detail="redirect_uri not registered for this client")

    user = users.authenticate(username, password)
    if not user:
        return HTMLResponse("<html><body><h3>Invalid username or password.</h3></body></html>", status_code=401)

    code = codes.issue(user["sub"], client_id, redirect_uri)
    separator = "&" if "?" in redirect_uri else "?"
    location = f"{redirect_uri}{separator}code={code}"
    if state:
        location += f"&state={state}"
    return RedirectResponse(url=location, status_code=302)


@router.post("/token")
def token(grant_type: str = Form(...), code: str = Form(...), redirect_uri: str = Form(...), client_id: str = Form(...), client_secret: str = Form(...)):
    if grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail="only grant_type=authorization_code is supported")
    if not client_store.verify_client_secret(client_id, client_secret):
        raise HTTPException(status_code=401, detail="invalid client credentials")

    sub = codes.redeem(code, client_id, redirect_uri)
    if not sub:
        raise HTTPException(status_code=400, detail="invalid, expired, or already-used authorization code")

    user = users.get_by_sub(sub)
    if not user:
        raise HTTPException(status_code=400, detail="user no longer exists")

    id_token = tokens.issue_id_token(user, client_id)
    return {
        "access_token": id_token,
        "id_token": id_token,
        "token_type": "Bearer",
        "expires_in": tokens.ACCESS_TOKEN_TTL_SECONDS,
    }


@router.get("/userinfo")
def userinfo(authorization: str = Header(default=None)):
    """Real Bearer-gated claims lookup — re-decodes the caller's own token
    (no separate session store) to find `sub`, then returns that real
    user's current record. Signature/expiry validation for OTHER services
    consuming these tokens lives in governance's own oidc.py — this
    endpoint trusts its own freshly-issued tokens by construction, same
    scope every other service's own /userinfo-equivalent has."""
    import jwt as pyjwt

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token_str = authorization[len("Bearer "):]
    try:
        claims = pyjwt.decode(token_str, keys.load_private_key().public_key(), algorithms=["RS256"], options={"verify_aud": False})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"invalid token: {e}")
    return {"sub": claims["sub"], "email": claims["email"], "role": claims["role"], "preferred_username": claims["preferred_username"]}
