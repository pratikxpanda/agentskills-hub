"""API-key minting and verification.

Only a hash of the secret is ever stored. The plaintext token exists once, in the response that
creates it, and is unrecoverable afterwards.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from functools import cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

TOKEN_SCHEME = "ashub"
_PREFIX_BYTES = 6
_SECRET_BYTES = 32

_hasher = PasswordHasher()


@cache
def _decoy_hash() -> str:
    """A hash to verify against when no key was found, so both paths do the same work."""
    return _hasher.hash(secrets.token_hex(_SECRET_BYTES))


@dataclass(frozen=True)
class MintedApiKey:
    token: str
    prefix: str
    key_hash: str


def mint_api_key() -> MintedApiKey:
    # Hex on both halves: token_urlsafe emits underscores, which would break the token's own
    # separator.
    prefix = secrets.token_hex(_PREFIX_BYTES)
    secret = secrets.token_hex(_SECRET_BYTES)
    return MintedApiKey(
        token=f"{TOKEN_SCHEME}_{prefix}_{secret}",
        prefix=prefix,
        key_hash=_hasher.hash(secret),
    )


def split_token(token: str) -> tuple[str, str] | None:
    parts = token.split("_")
    if len(parts) != 3 or parts[0] != TOKEN_SCHEME:
        return None
    _, prefix, secret = parts
    if not prefix or not secret:
        return None
    return prefix, secret


def verify_secret(key_hash: str | None, secret: str) -> bool:
    """Verify a secret, doing the same work whether or not a key was found.

    `key_hash` is `None` when no key matched the prefix. The comparison still runs against a decoy
    so an unknown prefix and a wrong secret cost the same.
    """
    try:
        _hasher.verify(key_hash if key_hash is not None else _decoy_hash(), secret)
    except (VerificationError, InvalidHashError):
        return False
    return key_hash is not None
