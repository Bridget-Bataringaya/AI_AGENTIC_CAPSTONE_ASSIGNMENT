"""Shared pytest fixtures and path setup."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

SAMPLES = REPO_ROOT / "knowledge" / "samples"


@pytest.fixture
def sample_checklist_path() -> Path:
    return SAMPLES / "checklist.csv"


@pytest.fixture
def sample_submission_path() -> Path:
    return SAMPLES / "synthetic-submission.pdf"


@pytest.fixture
def settings():
    from procurecheck.config import Settings

    return Settings()
