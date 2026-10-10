"""Verify every member token with Supabase Auth; never trust browser claims."""

import base64
import json
import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from uuid import UUID

import requests
from fastapi import Header, HTTPException


@dataclass(frozen=True)
class Member:
    id: str
    display_name: str


def _public_key(value: str) -> bool:
    if re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{16,}", value):
        return True
    # Legacy anon keys are public JWTs. Decoding here classifies server config;
    # this never validates a member's bearer token or grants access.
    parts = value.split(".")
    if len(parts) != 3:
        return False
    try:
        claims = json.loads(base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4)))
        return isinstance(claims, dict) and claims.get("role") == "anon"
    except (ValueError, TypeError, UnicodeError):
        return False


def auth_config():
    url = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    key = (os.getenv("SUPABASE_PUBLISHABLE_KEY", "").strip()
           or os.getenv("SUPABASE_ANON_KEY", "").strip())
    try:
        parsed = urlsplit(url)
        valid_url = (parsed.scheme == "https" and bool(parsed.hostname)
                     and not parsed.username and not parsed.password
                     and not parsed.path and not parsed.query and not parsed.fragment
                     and parsed.port in (None, 443))
    except ValueError:
        valid_url = False
    enabled = bool(valid_url and _public_key(key))
    # In particular, do not echo a mistakenly configured service-role/secret key.
    return {"enabled": enabled, "supabase_url": url if enabled else "",
            "supabase_publishable_key": key if enabled else "", "provider": "google"}


def unauthorized():
    return HTTPException(status_code=401, detail="Google 로그인이 필요합니다. 다시 로그인해 주세요.",
                         headers={"WWW-Authenticate": "Bearer"})


def optional_member(authorization: str | None = Header(default=None)) -> Member | None:
    if authorization is None:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token or len(token) > 8192 or any(c.isspace() for c in token):
        raise unauthorized()
    config = auth_config()
    if not config["enabled"]:
        raise HTTPException(status_code=503, detail="Google 로그인 설정을 준비 중입니다.")
    try:
        result = requests.get(
            config["supabase_url"] + "/auth/v1/user",
            headers={"apikey": config["supabase_publishable_key"], "Authorization": "Bearer " + token},
            timeout=(3, 8), allow_redirects=False,
        )
    except requests.RequestException:
        raise HTTPException(status_code=503, detail="로그인 확인 서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.") from None
    if result.status_code in (401, 403):
        raise unauthorized()
    if result.status_code != 200:
        raise HTTPException(status_code=503, detail="로그인 확인 서버를 일시적으로 사용할 수 없습니다.")
    try:
        user = result.json()
    except (ValueError, TypeError):
        raise HTTPException(status_code=503, detail="로그인 확인 응답을 처리할 수 없습니다.") from None
    if not isinstance(user, dict):
        raise unauthorized()
    try:
        user_id = str(UUID(user.get("id", "")))
    except (ValueError, TypeError, AttributeError):
        raise unauthorized() from None
    metadata = user.get("app_metadata") or {}
    identities = user.get("identities") or []
    # app_metadata and identities come from Auth, unlike editable user_metadata.
    providers = metadata.get("providers", []) if isinstance(metadata, dict) else []
    google = (isinstance(providers, list) and "google" in providers) or (
        isinstance(identities, list) and any(isinstance(i, dict) and i.get("provider") == "google" for i in identities)
    )
    if not google or not user.get("email_confirmed_at") or not user.get("email") or user.get("is_anonymous"):
        raise unauthorized()
    profile = user.get("user_metadata") or {}
    name = (profile.get("full_name") or profile.get("name") or "회원") if isinstance(profile, dict) else "회원"
    name = " ".join(str(name).split())[:60]
    # Do not accidentally publish an email address as the default public name.
    if not name or "@" in name:
        name = "회원"
    return Member(id=user_id, display_name=name)


def require_member(authorization: str | None = Header(default=None)) -> Member:
    member = optional_member(authorization)
    if member is None:
        raise unauthorized()
    return member
