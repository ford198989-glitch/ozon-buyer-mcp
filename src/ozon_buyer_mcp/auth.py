"""OAuth bearer validation for personal Ozon data exposed through MCP."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.parse import urlsplit

import jwt
from mcp.server.auth.provider import AccessToken
from mcp.server.auth.settings import AuthSettings


@dataclass(frozen=True)
class AuthConfig:
    domain: str
    audience: str
    scope: str
    subject: str

    @property
    def issuer(self) -> str:
        return f"https://{self.domain}/"

    @property
    def jwks_url(self) -> str:
        return f"https://{self.domain}/.well-known/jwks.json"


def auth_config(environment: Mapping[str, str] | None = None) -> AuthConfig:
    values = os.environ if environment is None else environment
    domain = values.get("AUTH0_DOMAIN", "").strip().removeprefix("https://").rstrip("/")
    audience = values.get("AUTH0_AUDIENCE", "").strip().rstrip("/")
    scope = values.get("AUTH0_REQUIRED_SCOPE", "ozon:read").strip()
    subject = values.get("AUTH0_ALLOWED_SUBJECT", "").strip()

    if not re.fullmatch(r"[A-Za-z0-9.-]+", domain or "") or "." not in domain:
        raise RuntimeError("AUTH0_DOMAIN must be a valid HTTPS Auth0 tenant domain")
    url = urlsplit(audience)
    if url.scheme != "https" or not url.netloc or url.path != "/mcp" or url.query or url.fragment:
        raise RuntimeError("AUTH0_AUDIENCE must be the canonical HTTPS /mcp URL")
    if not scope or any(char.isspace() for char in scope):
        raise RuntimeError("AUTH0_REQUIRED_SCOPE must be one scope name")
    if not subject:
        raise RuntimeError("AUTH0_ALLOWED_SUBJECT is required for personal Ozon data")
    return AuthConfig(domain=domain, audience=audience, scope=scope, subject=subject)


class Auth0TokenVerifier:
    def __init__(self, config: AuthConfig):
        self.config = config
        self._jwks = jwt.PyJWKClient(config.jwks_url, cache_keys=True, lifespan=3600)

    async def verify_token(self, token: str) -> AccessToken | None:
        try:
            claims = await asyncio.to_thread(self._decode, token)
        except (jwt.PyJWTError, OSError, TimeoutError):
            return None

        if claims.get("sub") != self.config.subject:
            return None
        scopes = str(claims.get("scope") or "").split()
        permissions = claims.get("permissions")
        if isinstance(permissions, list):
            scopes.extend(value for value in permissions if isinstance(value, str))
        if self.config.scope not in scopes:
            return None
        client_id = claims.get("azp") or claims.get("client_id") or claims.get("sub")
        if not isinstance(client_id, str) or not client_id:
            return None
        return AccessToken(
            token=token,
            client_id=client_id,
            scopes=list(dict.fromkeys(scopes)),
            expires_at=claims.get("exp") if isinstance(claims.get("exp"), int) else None,
            resource=self.config.audience,
            subject=self.config.subject,
        )

    def _decode(self, token: str) -> dict[str, Any]:
        key = self._jwks.get_signing_key_from_jwt(token).key
        return jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=self.config.audience,
            issuer=self.config.issuer,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=60,
        )


def mcp_auth_options(config: AuthConfig) -> dict[str, Any]:
    return {
        "auth": AuthSettings(
            issuer_url=config.issuer,
            resource_server_url=config.audience,
            required_scopes=[config.scope],
            validate_token_resource=False,
        ),
        "token_verifier": Auth0TokenVerifier(config),
    }
