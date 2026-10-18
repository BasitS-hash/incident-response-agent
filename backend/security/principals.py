"""Who an API key says you are.

The approval gate is the point of this system: nothing is sent until a human
accepts it, and ``audit_chain`` then attests to the row that records who did.
That attestation is only worth anything if the name in it is not something the
caller typed. Before this module, ``approver`` came straight from the request
body behind a single shared ``X-API-Key`` — so anyone holding the key could
approve as "the-cto", and the chain would verifiably vouch for it.

So identity is bound to the credential instead. ``API_KEYS`` maps keys to named
principals, the handler derives the approver from the key that authenticated the
call, and a body that disagrees with its credential is refused rather than
quietly overridden.

Each entry is ``principal:scopes:key``:

    API_KEYS=alice@corp.com:submit+approve:<key>,pager-bot:submit:<key>

Only the first two colons separate fields, so a key may contain colons. Entries
are split on commas and newlines, which a key therefore may not contain — the
constraint is cheap to live with for a random secret and it keeps the format
readable in a ``.env`` file. Scopes are split because filing an incident is not
the same authority as authorising a page: a webhook that opens incidents wants
``submit`` and nothing else.

**What this establishes, and what it does not.** A static key mapped to a name
is attribution to whoever holds that key, not authentication of a person. A
leaked key is an impersonation that every control here will happily attest to,
and nothing in this file can tell the difference. What it does buy: the name in
the audit row is chosen by whoever configured the deployment rather than by the
caller, and a key can be scoped and revoked. Real per-human identity needs
SSO/OIDC with per-user tokens — see the README's security section.

Three principals are not configured but derived, and each one is deliberate:

* ``SHARED_KEY_PRINCIPAL`` — the legacy single ``API_KEY``. It still
  authenticates and may still submit, but it names nobody, so it does not carry
  ``approve``. An approval under it would put a run through the gate with no
  identity attached, which is the gap this module exists to close.
* ``DEV_MODE_PRINCIPAL`` — no keys configured at all. That is the documented
  local dev mode and ``validate_config`` warns loudly about it; refusing
  approvals outright would break the local demo, so the approval is recorded
  under a name that says plainly that nobody was authenticated.
* nobody at all (``None``) — a key that matches nothing. Refused.
"""
from __future__ import annotations

import hmac
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

SCOPE_SUBMIT = "submit"
SCOPE_APPROVE = "approve"
_KNOWN_SCOPES = frozenset({SCOPE_SUBMIT, SCOPE_APPROVE})

# The principal name is written into the audit row's ``approver`` column, so it
# keeps the shape that column has always had — a config typo cannot put a
# newline or a control character into the log.
_NAME_RE = re.compile(r"^[\w\s.\-@']+$")
MAX_NAME_CHARS = 100

# Not enforced: a short key is a bad key, but refusing to start over it would
# turn a weak-secret warning into an outage. Warned about instead.
MIN_KEY_CHARS = 16

_ENTRY_SPLIT_RE = re.compile(r"[,\n]")


@dataclass(frozen=True)
class Principal:
    """An identity an API key resolves to, and what that identity may do."""

    name: str
    scopes: frozenset[str] = field(default_factory=frozenset)

    def can(self, scope: str) -> bool:
        return scope in self.scopes


# The legacy shared key authenticates, and names nobody. See the module note.
SHARED_KEY_PRINCIPAL = Principal(
    name="shared-key-unnamed", scopes=frozenset({SCOPE_SUBMIT})
)

# No keys configured: auth is off and the recorded approver says so.
DEV_MODE_PRINCIPAL = Principal(
    name="dev-mode-unauthenticated",
    scopes=frozenset({SCOPE_SUBMIT, SCOPE_APPROVE}),
)


@dataclass(frozen=True)
class ApiKeyConfig:
    """The result of reading ``API_KEYS``.

    ``errors`` are fatal and ``principals`` is empty when there are any: half a
    key configuration is worse than none, because the half that silently did not
    load may be the entry someone thought they had revoked.
    """

    principals: Mapping[str, Principal] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def parse_api_keys(raw: str) -> ApiKeyConfig:
    """Parse ``API_KEYS`` into a key → principal mapping.

    Messages identify an entry by its position and never quote the entry's
    contents: the thing most likely to be malformed is the key itself, and a
    config error that prints key material into a startup log has done more
    damage than the typo it was reporting.
    """
    principals: dict[str, Principal] = {}
    errors: list[str] = []
    warnings: list[str] = []

    entries = [e.strip() for e in _ENTRY_SPLIT_RE.split(raw)]
    position = 0
    for entry in entries:
        if not entry:
            continue
        position += 1
        where = f"API_KEYS entry {position}"

        parts = entry.split(":", 2)
        if len(parts) != 3:
            errors.append(f"{where}: expected 'principal:scopes:key'")
            continue

        name, scope_text, key = parts[0].strip(), parts[1].strip(), parts[2].strip()

        if not name or len(name) > MAX_NAME_CHARS or not _NAME_RE.match(name):
            errors.append(
                f"{where}: principal name is empty, over {MAX_NAME_CHARS} "
                f"characters, or outside the audit log's allowed charset"
            )
            continue

        scopes = {s.strip() for s in scope_text.split("+") if s.strip()}
        if not scopes:
            errors.append(f"{where}: no scopes — expected submit and/or approve")
            continue
        unknown = sorted(scopes - _KNOWN_SCOPES)
        if unknown:
            errors.append(
                f"{where}: unknown scope(s) {', '.join(unknown)} — "
                f"expected submit and/or approve"
            )
            continue

        if not key:
            errors.append(f"{where}: the key is empty")
            continue
        if key in principals:
            # Letting one entry win would silently decide which principal an
            # audit row blames for an approval.
            errors.append(f"{where}: this key is already used by an earlier entry")
            continue
        if len(key) < MIN_KEY_CHARS:
            warnings.append(
                f"{where}: the key is shorter than {MIN_KEY_CHARS} characters — "
                f"it is a bearer secret, generate a long random one"
            )

        principals[key] = Principal(name=name, scopes=frozenset(scopes))

    if errors:
        return ApiKeyConfig(errors=tuple(errors), warnings=tuple(warnings))
    return ApiKeyConfig(principals=principals, warnings=tuple(warnings))


def resolve_principal(
    key: str | None,
    *,
    named: Mapping[str, Principal],
    shared_key: str,
) -> Principal | None:
    """Resolve the presented key to a principal, or ``None`` for nobody.

    Named keys are checked first so a key that appears in both ``API_KEYS`` and
    ``API_KEY`` resolves to its name rather than to the anonymous shared
    principal. Comparison is constant-time: these are bearer secrets, and a
    plain ``==`` over a handful of them leaks how much of a guess was right.
    """
    if not named and not shared_key:
        return DEV_MODE_PRINCIPAL
    if not key:
        return None
    for candidate, principal in named.items():
        if hmac.compare_digest(key, candidate):
            return principal
    if shared_key and hmac.compare_digest(key, shared_key):
        return SHARED_KEY_PRINCIPAL
    return None
