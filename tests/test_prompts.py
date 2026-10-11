"""Prompt registry and version selection tests.

These cover the contract between configuration and the prompt registry: that a
numbered version plus a matching strategy resolves to exactly one registered
prompt, that an unknown version fails loudly rather than silently falling back
to a default, and that the v1.0 text stays byte-identical to the signed Prompt
Specification while v2.0 carries the rules the iteration was made for.
"""

from __future__ import annotations

import pytest

from procurecheck.config import STRATEGY_BATCH, STRATEGY_PER_ITEM, Settings
from procurecheck.prompts import (
    PROMPT_REGISTRY,
    PROMPT_VERSION_V1_0,
    PROMPT_VERSION_V1_0_PER_ITEM,
    PROMPT_VERSION_V2_0,
    PROMPT_VERSION_V2_0_PER_ITEM,
    SELECTABLE_PROMPT_VERSIONS,
    get_prompt,
    resolve_prompt_version,
)


def test_every_selectable_version_has_both_forms():
    for version in SELECTABLE_PROMPT_VERSIONS:
        assert version in PROMPT_REGISTRY
        assert f"{version}-per-item" in PROMPT_REGISTRY


def test_resolve_picks_the_per_item_form_for_the_per_item_strategy():
    assert resolve_prompt_version("v2.0", per_item=True) == PROMPT_VERSION_V2_0_PER_ITEM
    assert resolve_prompt_version("v2.0", per_item=False) == PROMPT_VERSION_V2_0
    assert resolve_prompt_version("v1.0", per_item=True) == PROMPT_VERSION_V1_0_PER_ITEM


def test_resolve_rejects_an_unknown_version():
    with pytest.raises(KeyError):
        resolve_prompt_version("v9.9", per_item=True)


def test_get_prompt_rejects_an_unknown_version():
    with pytest.raises(KeyError):
        get_prompt("v9.9-per-item")


def test_settings_resolve_the_prompt_the_run_will_send():
    per_item = Settings(prompt_version="v2.0", strategy=STRATEGY_PER_ITEM)
    assert per_item.resolved_prompt_version == PROMPT_VERSION_V2_0_PER_ITEM

    batch = Settings(prompt_version="v1.0", strategy=STRATEGY_BATCH)
    assert batch.resolved_prompt_version == PROMPT_VERSION_V1_0


def test_settings_reject_an_unknown_prompt_version():
    with pytest.raises(ValueError, match="prompt_version"):
        Settings(prompt_version="v9.9")


@pytest.mark.parametrize(
    "version", [PROMPT_VERSION_V1_0, PROMPT_VERSION_V1_0_PER_ITEM]
)
def test_v1_0_keeps_the_wording_of_the_signed_specification(version):
    """v1.0 is a record of what was signed off, not a prompt to keep tuning."""
    prompt = get_prompt(version)
    assert "Public Procurement Completeness Clerk" in prompt
    # The iteration's additions must not leak backwards into the baseline, or
    # the recorded v1.0 evaluation could no longer be reproduced.
    assert "IDENTITY TEST" not in prompt
    assert "REPORTING ABSENCE" not in prompt
    assert "CONFIDENCE BANDS" not in prompt


@pytest.mark.parametrize(
    "version", [PROMPT_VERSION_V2_0, PROMPT_VERSION_V2_0_PER_ITEM]
)
def test_v2_0_carries_the_rules_the_iteration_was_made_for(version):
    prompt = get_prompt(version)
    for block in (
        "DECISION PROCEDURE",
        "REPORTING ABSENCE",
        "IDENTITY TEST",
        "CONFIDENCE BANDS",
        "EVIDENCE RULES",
        "FINAL CHECK",
    ):
        assert block in prompt, f"{version} is missing the {block} block"


@pytest.mark.parametrize("version", sorted(PROMPT_REGISTRY))
def test_no_prompt_names_a_document_from_the_evaluation_checklist(version):
    """Worked examples in a prompt must not encode the evaluation's answers.

    The identity test in v2.0 teaches by example. If those examples name the
    documents the evaluation cases turn on, the cases pass because the answer
    was handed to the model, and the evaluation stops measuring anything. The
    examples must therefore teach the principle using documents the checklist
    does not mention.
    """
    prompt = get_prompt(version).lower()
    # Distinctive terms from knowledge/samples/checklist.csv, kept as literals
    # so that editing the sample checklist cannot silently weaken this guard.
    for term in (
        "audited accounts",
        "audited financial statements",
        "bid security",
        "bid guarantee",
        "certificate of incorporation",
        "certificate of registration",
        "tax clearance",
        "anti-bribery",
        "beneficial ownership",
        "conflict of interest",
        "power of attorney",
        "non-blacklisting",
        "non-debarment",
        "declaration of interest",
    ):
        assert term not in prompt, (
            f"{version} names {term!r}, a document the evaluation cases turn on. "
            f"Use an example drawn from outside the sample checklist instead."
        )


@pytest.mark.parametrize("version", sorted(PROMPT_REGISTRY))
def test_every_prompt_keeps_the_safety_boundary(version):
    """The boundary is a requirement of the Boundary Matrix, not of a version."""
    prompt = get_prompt(version)
    assert "Do NOT output a score" in prompt
    assert "Do NOT rank, compare" in prompt
    assert "Do NOT comment on legal validity" in prompt
    assert "Do NOT recommend awarding" in prompt
    assert "ignore previous instructions" in prompt
