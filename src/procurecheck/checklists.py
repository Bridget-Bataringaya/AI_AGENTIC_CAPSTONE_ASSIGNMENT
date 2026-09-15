"""Bundled checklists.

A procurement checklist is normally written out afresh for every tender, which
means someone has to author a CSV before the agent can be run against a new
document at all. That is friction with no payoff during development and
testing, so one general-purpose checklist ships with the project and is used
whenever the caller does not name a file.

The bundled list is a STARTING TEMPLATE, not an authority. The documents a bid
must actually contain are fixed by the bidding document for that specific
tender. Anything produced against the bundled list says so, in the report, so
that a count of located items is never mistaken for compliance with a real
tender's requirements.

Bundled ids live in their own STD-nn namespace. They are fixed for the life of
the file and are never renumbered: expectation files, evaluation cases and past
reports all key off them, so reusing or shifting an id would silently
re-point every one of those references.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Final, List

# src/procurecheck/checklists.py -> src/procurecheck -> src -> repo root
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
CHECKLIST_DIR: Final[Path] = REPO_ROOT / "knowledge" / "checklists"

STANDARD: Final[str] = "standard"

# Names the caller may pass to --checklist instead of a path.
BUNDLED: Final[Dict[str, str]] = {
    STANDARD: "standard-procurement-checklist.csv",
}

# Shown in reports so a reader knows which list the findings were measured
# against, and how much authority it carries.
BUNDLED_LABEL: Final[Dict[str, str]] = {
    STANDARD: "Standard procurement checklist (bundled template)",
}

TEMPLATE_CAVEAT: Final[str] = (
    "This check used the bundled standard checklist, which is a general "
    "template. The documents a bid must actually contain are set by the "
    "bidding document for this tender. Edit the checklist to match it before "
    "relying on these findings."
)


class UnknownChecklistError(ValueError):
    """Raised when a checklist name is neither bundled nor an existing file."""


def bundled_names() -> List[str]:
    return sorted(BUNDLED)


def path_for(name: str) -> Path:
    """Absolute path of a bundled checklist."""
    try:
        return CHECKLIST_DIR / BUNDLED[name]
    except KeyError as exc:
        raise UnknownChecklistError(f"No bundled checklist named {name!r}.") from exc


def label_for(name: str) -> str:
    return BUNDLED_LABEL.get(name, name)


def is_bundled(name: str) -> bool:
    return name in BUNDLED


def resolve(value: str | Path | None) -> tuple[Path, str, bool]:
    """Turn a --checklist argument into a file to read.

    Accepts a bundled name ("standard"), a path to a checklist file, or None,
    which selects the standard checklist. Returns the path, a label naming the
    checklist for the report, and whether the bundled template was used.
    """
    if value is None:
        value = STANDARD

    text = str(value).strip()
    if is_bundled(text):
        path = path_for(text)
        if not path.is_file():
            raise UnknownChecklistError(
                f"The bundled checklist {text!r} is missing from {path}. "
                f"The file should be part of the repository."
            )
        return path, label_for(text), True

    path = Path(value)
    if not path.is_file():
        raise UnknownChecklistError(
            f"No such checklist file: {path}. Pass a path to a .csv, .txt, .md "
            f"or .pdf checklist, or one of the bundled names: "
            f"{', '.join(bundled_names())}."
        )
    return path, path.name, False
