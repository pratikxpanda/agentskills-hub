"""Token minting and verification."""

from __future__ import annotations

import pytest

from agentskills_hub_core.security import (
    TOKEN_SCHEME,
    mint_api_key,
    split_token,
    verify_secret,
)


def test_a_minted_token_carries_its_own_prefix() -> None:
    minted = mint_api_key()
    scheme, prefix, secret = minted.token.split("_")

    assert scheme == TOKEN_SCHEME
    assert prefix == minted.prefix
    assert len(secret) == 64  # 256 bits, hex


def test_the_secret_is_not_recoverable_from_the_stored_hash() -> None:
    minted = mint_api_key()
    _, _, secret = minted.token.split("_")

    assert secret not in minted.key_hash
    assert minted.key_hash.startswith("$argon2")


def test_two_mints_never_agree() -> None:
    assert mint_api_key().token != mint_api_key().token


def test_verification_accepts_the_right_secret_and_rejects_the_rest() -> None:
    minted = mint_api_key()
    _, _, secret = minted.token.split("_")
    # Flipped to a character the last one is not: appending a fixed digit reproduces the original
    # secret one time in sixteen, because the secret is hex.
    wrong = secret[:-1] + ("1" if secret[-1] == "0" else "0")

    assert verify_secret(minted.key_hash, secret) is True
    assert verify_secret(minted.key_hash, wrong) is False
    assert verify_secret(minted.key_hash, "") is False


def test_verification_against_no_key_still_returns_false() -> None:
    # The decoy path exists so an unknown prefix costs the same as a wrong secret.
    assert verify_secret(None, "anything") is False


@pytest.mark.parametrize(
    "token",
    ["", "garbage", "ashub", "ashub_prefix", "other_prefix_secret", "ashub_prefix_secret_extra"],
)
def test_malformed_tokens_do_not_parse(token: str) -> None:
    assert split_token(token) is None


def test_a_well_formed_token_parses() -> None:
    minted = mint_api_key()
    parsed = split_token(minted.token)

    assert parsed is not None
    assert parsed[0] == minted.prefix
