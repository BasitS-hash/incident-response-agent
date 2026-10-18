"""Tests for backend/security/principals.py — what an API key says you are.

The point of this module is that the name written into the audit row is derived
from the credential, never from the request body. These tests are mostly about
the two ways that can go wrong: a key that maps to nobody being treated as
somebody, and a parse error quietly dropping a key that was meant to work.
"""
from __future__ import annotations

from backend.security.principals import (
    DEV_MODE_PRINCIPAL,
    SCOPE_APPROVE,
    SCOPE_SUBMIT,
    SHARED_KEY_PRINCIPAL,
    Principal,
    parse_api_keys,
    resolve_principal,
)

# ── parsing ───────────────────────────────────────────────────────────────

class TestParseApiKeys:
    def test_blank_config_yields_no_principals(self) -> None:
        parsed = parse_api_keys("")
        assert parsed.principals == {}
        assert parsed.errors == ()

    def test_single_entry_maps_key_to_principal(self) -> None:
        parsed = parse_api_keys("alice@corp.com:approve:" + "k" * 24)
        assert parsed.errors == ()
        principal = parsed.principals["k" * 24]
        assert principal.name == "alice@corp.com"
        assert principal.scopes == frozenset({SCOPE_APPROVE})

    def test_multiple_scopes_are_split_on_plus(self) -> None:
        parsed = parse_api_keys("sre-oncall:submit+approve:" + "k" * 24)
        principal = parsed.principals["k" * 24]
        assert principal.scopes == frozenset({SCOPE_SUBMIT, SCOPE_APPROVE})

    def test_entries_separated_by_commas_and_newlines(self) -> None:
        parsed = parse_api_keys(
            "alice:approve:" + "a" * 24 + ",\n  bot:submit:" + "b" * 24 + "\n"
        )
        assert parsed.errors == ()
        assert parsed.principals["a" * 24].name == "alice"
        assert parsed.principals["b" * 24].name == "bot"

    def test_a_key_may_contain_colons(self) -> None:
        """Only the first two colons are separators — the rest is key material."""
        parsed = parse_api_keys("alice:approve:aa:bb:cc" + "d" * 18)
        assert parsed.errors == ()
        assert parsed.principals["aa:bb:cc" + "d" * 18].name == "alice"

    def test_too_few_fields_is_an_error(self) -> None:
        parsed = parse_api_keys("alice:" + "k" * 24)
        assert parsed.principals == {}
        assert len(parsed.errors) == 1
        assert "entry 1" in parsed.errors[0]

    def test_unknown_scope_is_an_error(self) -> None:
        parsed = parse_api_keys("alice:deploy:" + "k" * 24)
        assert parsed.principals == {}
        assert any("deploy" in e for e in parsed.errors)

    def test_empty_scope_list_is_an_error(self) -> None:
        parsed = parse_api_keys("alice::" + "k" * 24)
        assert parsed.principals == {}
        assert parsed.errors

    def test_principal_name_charset_is_enforced(self) -> None:
        """The name lands in the audit row, so it keeps the shape that column
        has always had — a config typo cannot put a newline in the log."""
        parsed = parse_api_keys("ali\nce:approve:" + "k" * 24)
        assert parsed.principals == {}
        assert parsed.errors

    def test_overlong_principal_name_is_an_error(self) -> None:
        parsed = parse_api_keys("A" * 101 + ":approve:" + "k" * 24)
        assert parsed.principals == {}
        assert parsed.errors

    def test_blank_key_is_an_error(self) -> None:
        parsed = parse_api_keys("alice:approve:")
        assert parsed.principals == {}
        assert parsed.errors

    def test_duplicate_key_for_two_principals_is_an_error(self) -> None:
        """Whichever entry won would decide who the audit row blames."""
        parsed = parse_api_keys(
            "alice:approve:" + "k" * 24 + ",bob:approve:" + "k" * 24
        )
        assert parsed.principals == {}
        assert any("entry 2" in e for e in parsed.errors)

    def test_two_keys_for_one_principal_are_allowed(self) -> None:
        """Key rotation: the same person holding an old and a new key."""
        parsed = parse_api_keys(
            "alice:approve:" + "a" * 24 + ",alice:approve:" + "b" * 24
        )
        assert parsed.errors == ()
        assert parsed.principals["a" * 24] == parsed.principals["b" * 24]

    def test_a_bad_entry_voids_the_whole_config(self) -> None:
        """Fail closed. Keeping the good half of a config nobody can read is
        how a key that was meant to be revoked stays live."""
        parsed = parse_api_keys("alice:approve:" + "a" * 24 + ",bob:nope:" + "b" * 24)
        assert parsed.principals == {}

    def test_errors_never_quote_key_material(self) -> None:
        secret = "s3cret-key-nobody-should-log"
        parsed = parse_api_keys("alice:deploy:" + secret)
        assert parsed.errors
        assert all(secret not in e for e in parsed.errors)

    def test_short_key_warns_but_is_accepted(self) -> None:
        parsed = parse_api_keys("alice:approve:short")
        assert parsed.errors == ()
        assert parsed.principals["short"].name == "alice"
        assert any("entry 1" in w for w in parsed.warnings)

    def test_warnings_never_quote_key_material(self) -> None:
        parsed = parse_api_keys("alice:approve:tiny")
        assert parsed.warnings
        assert all("tiny" not in w for w in parsed.warnings)

    def test_long_key_does_not_warn(self) -> None:
        parsed = parse_api_keys("alice:approve:" + "k" * 24)
        assert parsed.warnings == ()


# ── Principal.can ─────────────────────────────────────────────────────────

class TestPrincipalScopes:
    def test_holds_the_scope_it_was_given(self) -> None:
        p = Principal(name="alice", scopes=frozenset({SCOPE_APPROVE}))
        assert p.can(SCOPE_APPROVE)

    def test_does_not_hold_a_scope_it_was_not_given(self) -> None:
        p = Principal(name="alice", scopes=frozenset({SCOPE_SUBMIT}))
        assert not p.can(SCOPE_APPROVE)


# ── resolution ────────────────────────────────────────────────────────────

class TestResolvePrincipal:
    _NAMED = {"alice-key-aaaaaaaaaaaaaaaa": Principal(
        name="alice@corp.com", scopes=frozenset({SCOPE_SUBMIT, SCOPE_APPROVE})
    )}

    def test_named_key_resolves_to_its_principal(self) -> None:
        p = resolve_principal(
            "alice-key-aaaaaaaaaaaaaaaa", named=self._NAMED, shared_key="shared"
        )
        assert p is not None
        assert p.name == "alice@corp.com"

    def test_unknown_key_resolves_to_nobody(self) -> None:
        assert resolve_principal("nope", named=self._NAMED, shared_key="shared") is None

    def test_missing_header_resolves_to_nobody(self) -> None:
        assert resolve_principal(None, named=self._NAMED, shared_key="shared") is None

    def test_shared_key_resolves_to_an_unnamed_principal(self) -> None:
        """The legacy single key still authenticates and can still file an
        incident, but it names nobody, so it carries no approve scope."""
        p = resolve_principal("shared", named=self._NAMED, shared_key="shared")
        assert p == SHARED_KEY_PRINCIPAL
        assert p.can(SCOPE_SUBMIT)
        assert not p.can(SCOPE_APPROVE)

    def test_named_key_wins_over_an_identical_shared_key(self) -> None:
        p = resolve_principal(
            "alice-key-aaaaaaaaaaaaaaaa",
            named=self._NAMED,
            shared_key="alice-key-aaaaaaaaaaaaaaaa",
        )
        assert p is not None
        assert p.name == "alice@corp.com"

    def test_no_configured_keys_at_all_is_dev_mode(self) -> None:
        """Auth off is the documented local-dev mode. The recorded principal
        then says so rather than borrowing a human's name."""
        p = resolve_principal(None, named={}, shared_key="")
        assert p == DEV_MODE_PRINCIPAL
        assert p.can(SCOPE_APPROVE)
        assert "unauthenticated" in p.name

    def test_dev_mode_ignores_whatever_key_was_sent(self) -> None:
        assert resolve_principal("anything", named={}, shared_key="") == DEV_MODE_PRINCIPAL

    def test_named_keys_alone_are_enough_to_turn_auth_on(self) -> None:
        """No API_KEY set, but API_KEYS is — that is not dev mode."""
        assert resolve_principal("nope", named=self._NAMED, shared_key="") is None
