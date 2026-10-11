"""Tests for the bundled checklist resolver.

The bundled list exists so that a new document can be checked without anyone
writing a checklist first. The two things that must hold are that it resolves
by default, and that its ids stay fixed: expectation files and past reports key
off STD-nn, so a shifted id would silently re-point every one of them.
"""

from __future__ import annotations

import csv

import pytest

from procurecheck import checklists
from procurecheck.ingestion import parse_checklist

EXPECTED_ITEM_COUNT = 22


def test_resolve_without_an_argument_returns_the_standard_checklist():
    path, label, is_template = checklists.resolve(None)

    assert path == checklists.path_for(checklists.STANDARD)
    assert path.is_file()
    assert label == checklists.BUNDLED_LABEL[checklists.STANDARD]
    assert is_template is True


def test_resolve_accepts_the_bundled_name():
    path, _label, is_template = checklists.resolve("standard")

    assert path.name == "standard-procurement-checklist.csv"
    assert is_template is True


def test_resolve_accepts_a_path_and_does_not_mark_it_a_template(tmp_path):
    custom = tmp_path / "tender-42.csv"
    custom.write_text("id,description\nA-1,Signed bid form\n", encoding="utf-8")

    path, label, is_template = checklists.resolve(custom)

    assert path == custom
    assert label == "tender-42.csv"
    assert is_template is False


def test_resolve_rejects_a_missing_file_and_names_the_bundled_options(tmp_path):
    with pytest.raises(checklists.UnknownChecklistError) as error:
        checklists.resolve(tmp_path / "does-not-exist.csv")

    assert "standard" in str(error.value)


def test_the_standard_checklist_parses_into_items():
    items = parse_checklist(checklists.path_for(checklists.STANDARD))

    assert len(items) == EXPECTED_ITEM_COUNT
    assert all(item.description for item in items)


def test_standard_ids_are_unique_sequential_and_in_their_own_namespace():
    """STD-nn, never CHK-nn, so a bundled id can never collide with a
    hand-written checklist's id in an expectations file."""
    items = parse_checklist(checklists.path_for(checklists.STANDARD))
    ids = [item.id for item in items]

    assert len(set(ids)) == len(ids)
    assert ids == [f"STD-{index:02d}" for index in range(1, len(ids) + 1)]


def test_every_row_of_the_standard_checklist_is_well_formed():
    """A stray comma in a description silently splits the row and drops text."""
    with checklists.path_for(checklists.STANDARD).open(encoding="utf-8") as handle:
        rows = list(csv.reader(handle))

    assert rows[0] == ["id", "category", "description"]
    assert all(len(row) == 3 for row in rows)
    assert all(row[1] and row[2] for row in rows[1:])


def test_the_template_caveat_tells_the_reader_to_edit_it():
    assert "bidding document" in checklists.TEMPLATE_CAVEAT
    assert "Edit the checklist" in checklists.TEMPLATE_CAVEAT
