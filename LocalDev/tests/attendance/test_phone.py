"""Phone normalization — pure logic, no I/O (api/phone.py)."""

from __future__ import annotations

import pytest

from api.phone import to_e164


# ── rule 3: bare 10-digit US numbers ──────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    [
        "5551110001",
        "555-111-0001",
        "(555) 111-0001",
        "555.111.0001",
        "  555 111 0001  ",
    ],
)
def test_ten_digit_us_number_gets_country_code(raw):
    assert to_e164(raw) == "+15551110001"


# ── rule 4: 11 digits already carrying the US country code ────────────────────

@pytest.mark.parametrize("raw", ["15551110001", "1 (555) 111-0001", "1-555-111-0001"])
def test_eleven_digits_leading_one(raw):
    assert to_e164(raw) == "+15551110001"


def test_eleven_digits_not_leading_one_is_rejected():
    # No country code can be inferred, so this is not a usable number.
    assert to_e164("25551110001") is None


# ── rule 2: explicit international form ───────────────────────────────────────

def test_already_e164_passes_through():
    assert to_e164("+15551110001") == "+15551110001"


def test_international_number_is_kept_verbatim():
    assert to_e164("+44 20 7946 0958") == "+442079460958"


def test_plus_with_minimum_digits_is_accepted():
    assert to_e164("+12345678") == "+12345678"


def test_plus_with_maximum_digits_is_accepted():
    assert to_e164("+" + "1" * 15) == "+" + "1" * 15


def test_plus_below_minimum_digits_is_rejected():
    assert to_e164("+1234567") is None


def test_plus_above_maximum_digits_is_rejected():
    assert to_e164("+" + "1" * 16) is None


# ── rule 5 / rule 1: everything else ──────────────────────────────────────────

def test_nine_digit_legacy_seed_value_is_rejected():
    # The pre-0149 seed format ("555111001") — unparseable, must normalize to NULL.
    assert to_e164("555111001") is None


@pytest.mark.parametrize(
    "raw",
    [None, "", "   ", "\t\n", "not a phone", "555-CALL", "+", "+++", "0"],
)
def test_garbage_input_is_rejected(raw):
    assert to_e164(raw) is None


def test_double_plus_uses_the_international_branch():
    # Leading '+' wins; the stray second '+' is just a non-digit character.
    assert to_e164("++15551110001") == "+15551110001"


@pytest.mark.parametrize("raw", [12345678901, 5551110001, [], {}, object()])
def test_non_string_input_is_rejected(raw):
    assert to_e164(raw) is None


def test_surrounding_letters_are_stripped_before_counting_digits():
    assert to_e164("call me at 555-111-0001 ok") == "+15551110001"


def test_extension_suffix_makes_the_number_unparseable():
    # "5551110001 x22" -> 12 digits, matches no rule; better to reject than to guess.
    assert to_e164("5551110001 x22") is None


# ── invariants ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "raw",
    ["5551110001", "+15551110001", "1-555-111-0001", "+44 20 7946 0958"],
)
def test_normalization_is_idempotent(raw):
    once = to_e164(raw)
    assert once is not None
    assert to_e164(once) == once


@pytest.mark.parametrize(
    "raw",
    ["5551110001", "+15551110001", "+442079460958", "555111001", "", None, "garbage"],
)
def test_output_is_always_none_or_valid_e164(raw):
    import re

    out = to_e164(raw)
    assert out is None or re.fullmatch(r"\+[0-9]{8,15}", out), out
