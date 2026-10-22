"""Uploaded checklist and submission must remain independent inputs."""

from io import BytesIO

from fastapi import UploadFile

from procurecheck import api


def upload(content):
    return UploadFile(filename="document.txt", file=BytesIO(content))


def test_same_named_uploads_preserve_both_contents(tmp_path):
    checklist = api._save_upload(upload(b"Tax clearance certificate"), tmp_path)
    submission = api._save_upload(upload(b"Bidder registration only"), tmp_path)
    assert checklist.read_bytes() == b"Tax clearance certificate"
    assert submission.read_bytes() == b"Bidder registration only"
    assert checklist.name == submission.name == "document.txt"


def test_read_uploads_does_not_check_the_checklist_as_the_submission():
    _, items, parsed = api._read_uploads(
        upload(b"Bidder registration only"),
        upload(b"Tax clearance certificate"),
    )
    assert [item.description for item in items] == ["Tax clearance certificate"]
    assert "Bidder registration only" in parsed.as_marked_text()
    assert "Tax clearance certificate" not in parsed.as_marked_text()
