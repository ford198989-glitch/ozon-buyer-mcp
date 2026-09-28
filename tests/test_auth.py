import asyncio
import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from ozon_buyer_mcp.auth import Auth0TokenVerifier, auth_config
from ozon_buyer_mcp.parsers import product_path


CONFIG = {
    "AUTH0_DOMAIN": "example.eu.auth0.com",
    "AUTH0_AUDIENCE": "https://ozon.example.com/mcp",
    "AUTH0_REQUIRED_SCOPE": "ozon:read",
    "AUTH0_ALLOWED_SUBJECT": "auth0|owner",
}


def test_personal_mcp_requires_exact_owner_and_resource():
    config = auth_config(CONFIG)
    verifier = Auth0TokenVerifier(config)
    claims = {"sub": "auth0|owner", "scope": "ozon:read", "azp": "chatgpt", "exp": 2_000_000_000}
    verifier._decode = lambda token: claims
    access = asyncio.run(verifier.verify_token("test-token"))
    assert access is not None
    assert access.subject == "auth0|owner"
    assert access.resource == CONFIG["AUTH0_AUDIENCE"]

    claims["sub"] = "auth0|someone-else"
    assert asyncio.run(verifier.verify_token("test-token")) is None
    claims["sub"] = "auth0|owner"
    claims["scope"] = "unrelated:read"
    assert asyncio.run(verifier.verify_token("test-token")) is None


def test_auth0_verifier_checks_signature_issuer_and_audience():
    config = auth_config(CONFIG)
    verifier = Auth0TokenVerifier(config)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    verifier._jwks.get_signing_key_from_jwt = lambda token: SimpleNamespace(key=key.public_key())
    claims = {
        "sub": config.subject,
        "scope": config.scope,
        "iss": config.issuer,
        "aud": config.audience,
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
    }
    valid = jwt.encode(claims, key, algorithm="RS256")
    assert asyncio.run(verifier.verify_token(valid)) is not None
    other_audience = jwt.encode({**claims, "aud": "https://another.example.com/mcp"}, key, algorithm="RS256")
    assert asyncio.run(verifier.verify_token(other_audience)) is None
    other_issuer = jwt.encode({**claims, "iss": "https://other.example.com/"}, key, algorithm="RS256")
    assert asyncio.run(verifier.verify_token(other_issuer)) is None


@pytest.mark.parametrize("missing", ["AUTH0_DOMAIN", "AUTH0_AUDIENCE", "AUTH0_ALLOWED_SUBJECT"])
def test_personal_mcp_fails_closed_when_configuration_is_incomplete(missing):
    values = CONFIG.copy()
    values.pop(missing)
    with pytest.raises(RuntimeError):
        auth_config(values)


@pytest.mark.parametrize("value", [
    "https://other.example.com/product/foo-1185261285/",
    "https://www.ozon.ru/my/orderlist/",
    "/my/orderlist/",
    "/product/foo-1185261285/?redirect=/my/orderlist/",
])
def test_product_argument_cannot_reach_account_pages(value):
    with pytest.raises(ValueError):
        product_path(value)
