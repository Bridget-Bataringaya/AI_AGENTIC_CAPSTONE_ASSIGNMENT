"""Who may call which tool.

The Tool / Function Specification requires both tools to refuse callers who
are not authenticated or not permitted. That check runs here, in the
application, before a tool runs, and never in a prompt: a model cannot be
trusted to enforce a permission it can be talked out of.

Each tool names one permission. Each role grants a set of permissions. A caller
with no identity at all is refused outright.

Roles follow the actors in the Project Charter. A procurement officer runs
checks and reads their reports. An evaluation committee member reads reports
but does not start checks. A bidder and a guest may do neither: a bidder must
never see another bidder's findings, and the completeness check is an internal
step of the preliminary examination.

Scope note: permissions are per role, not per document. The specification also
asks that a user be allowed to access the particular document; nothing in the
application yet records who owns which submission, so that part is not
enforced and is recorded as open work in docs/architecture/tool-calling.md.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Dict, Final, FrozenSet, Mapping, Optional

PERMISSION_ANALYSE: Final[str] = "document:analyse"
PERMISSION_REPORT: Final[str] = "report:generate"

ROLE_PROCUREMENT_OFFICER: Final[str] = "procurement_officer"
ROLE_EVALUATION_COMMITTEE: Final[str] = "evaluation_committee"
ROLE_BIDDER: Final[str] = "bidder"
ROLE_GUEST: Final[str] = "guest"

ROLE_PERMISSIONS: Final[Mapping[str, FrozenSet[str]]] = {
    ROLE_PROCUREMENT_OFFICER: frozenset({PERMISSION_ANALYSE, PERMISSION_REPORT}),
    ROLE_EVALUATION_COMMITTEE: frozenset({PERMISSION_REPORT}),
    ROLE_BIDDER: frozenset(),
    ROLE_GUEST: frozenset(),
}

API_KEYS_ENV: Final[str] = "PROCURECHECK_API_KEYS"


@dataclass(frozen=True)
class Principal:
    """An authenticated caller."""

    user_id: str
    role: str

    @property
    def permissions(self) -> FrozenSet[str]:
        return ROLE_PERMISSIONS.get(self.role, frozenset())

    def may(self, permission: str) -> bool:
        return permission in self.permissions


def is_permitted(principal: Optional[Principal], permission: str) -> bool:
    """False for an anonymous caller, an unknown role, or a missing permission."""
    return principal is not None and principal.may(permission)


class ApiKeyError(ValueError):
    """Raised when PROCURECHECK_API_KEYS is malformed."""


def load_api_keys(raw: Optional[str] = None) -> Dict[str, Principal]:
    """Parse `key:role:user_id` entries, separated by commas.

    Read from the environment, never from code, so no credential is committed.
    An empty or unset variable yields no keys, which makes every authenticated
    endpoint refuse: the API fails closed rather than open.
    """
    value = os.getenv(API_KEYS_ENV, "") if raw is None else raw
    keys: Dict[str, Principal] = {}
    entries = [part.strip() for part in value.split(",")]
    for position, entry in enumerate(filter(None, entries), start=1):
        parts = entry.split(":")
        if len(parts) != 3 or not all(p.strip() for p in parts):
            # The entry is never quoted: it holds a secret, and this message
            # can reach a log or, through a careless handler, a client.
            raise ApiKeyError(
                f"{API_KEYS_ENV} entry {position} must look like key:role:user_id "
                f"(it has {len(parts)} part(s))."
            )
        key, role, user_id = (p.strip() for p in parts)
        if role not in ROLE_PERMISSIONS:
            raise ApiKeyError(
                f"Unknown role {role!r} in {API_KEYS_ENV} entry {position}. "
                f"Known roles: {', '.join(sorted(ROLE_PERMISSIONS))}."
            )
        keys[key] = Principal(user_id=user_id, role=role)
    return keys


def principal_for_key(api_key: Optional[str], keys: Mapping[str, Principal]) -> Optional[Principal]:
    """Constant-time comparison, so response timing does not leak a key."""
    if not api_key:
        return None
    for key, principal in keys.items():
        if hmac.compare_digest(key.encode(), api_key.encode()):
            return principal
    return None
