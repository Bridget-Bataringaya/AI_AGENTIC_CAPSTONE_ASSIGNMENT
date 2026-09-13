"""FastAPI backend.

The API / Backend Service from the Architecture and Context Diagram (Sec. 4).
It orchestrates ingestion, the Safety Guard, the Matching Engine and the Report
Generator for a single in-progress completeness check.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import Settings
from .engine import ContextOverflowError, MatchingEngine
from .ingestion import (
    EmptyChecklistError,
    EmptyDocumentError,
    UnsupportedDocumentError,
    parse_checklist,
    parse_submission,
)
from .llm import ModelUnavailableError, OllamaClient
from .models import ChecklistItem, ItemStatus
from .report import to_csv, to_dict
from .safety import MultipleSubmissionsError, assert_single_submission

HTTP_BAD_REQUEST = 400
HTTP_UNPROCESSABLE = 422
HTTP_SERVICE_UNAVAILABLE = 503

app = FastAPI(
    title="Public Procurement Document-Completeness Agent",
    description=(
        "Checks a tender submission against a published checklist and reports "
        "which required items are present, missing, or need human review. "
        "It does not score, rank, evaluate legal validity, or recommend awards."
    ),
    version="0.1.0",
)


def get_settings() -> Settings:
    return Settings.from_env()


class ChecklistResponse(BaseModel):
    items: List[ChecklistItem]
    count: int


class OverrideRequest(BaseModel):
    """Manual override of a Requires Human Review item (User Stories AC10)."""

    checklist_item_id: str
    status: ItemStatus = Field(description="Resolve to Found or Not Found")


def _save_upload(upload: UploadFile, directory: Path) -> Path:
    if not upload.filename:
        raise HTTPException(HTTP_BAD_REQUEST, "The uploaded file has no filename.")
    destination = directory / Path(upload.filename).name
    destination.write_bytes(upload.file.read())
    return destination


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Confirm the backend and the model are both reachable."""
    try:
        with OllamaClient(settings) as client:
            return {"status": "ok", **client.health()}
    except ModelUnavailableError as exc:
        raise HTTPException(HTTP_SERVICE_UNAVAILABLE, str(exc)) from exc


@app.post("/checklist/parse", response_model=ChecklistResponse)
def parse_checklist_endpoint(file: UploadFile = File(...)) -> ChecklistResponse:
    """Extract required items from a checklist so the user can edit them
    before running a check (User Stories AC1)."""
    with tempfile.TemporaryDirectory() as workspace:
        path = _save_upload(file, Path(workspace))
        try:
            items = parse_checklist(path)
        except (UnsupportedDocumentError, EmptyChecklistError) as exc:
            raise HTTPException(HTTP_BAD_REQUEST, str(exc)) from exc
    return ChecklistResponse(items=items, count=len(items))


@app.post("/check")
def run_check(
    checklist: UploadFile = File(..., description="Checklist in PDF, CSV or TXT"),
    submission: UploadFile = File(..., description="One tender submission"),
    instruction: Optional[str] = Form(default=None),
    output_format: str = Form(default="json"),
    settings: Settings = Depends(get_settings),
):
    """Run a completeness check for exactly one submission."""
    if output_format not in ("json", "csv"):
        raise HTTPException(HTTP_BAD_REQUEST, "output_format must be 'json' or 'csv'.")

    try:
        assert_single_submission(1)
    except MultipleSubmissionsError as exc:
        raise HTTPException(HTTP_BAD_REQUEST, str(exc)) from exc

    with tempfile.TemporaryDirectory() as workspace:
        directory = Path(workspace)
        checklist_path = _save_upload(checklist, directory)
        submission_path = _save_upload(submission, directory)

        try:
            items = parse_checklist(checklist_path)
            parsed = parse_submission(submission_path)
        except (UnsupportedDocumentError, EmptyChecklistError, EmptyDocumentError) as exc:
            raise HTTPException(HTTP_BAD_REQUEST, str(exc)) from exc

        try:
            with OllamaClient(settings) as client:
                outcome = MatchingEngine(client, settings).analyse(items, parsed, instruction)
        except ModelUnavailableError as exc:
            raise HTTPException(HTTP_SERVICE_UNAVAILABLE, str(exc)) from exc
        except ContextOverflowError as exc:
            raise HTTPException(HTTP_UNPROCESSABLE, str(exc)) from exc

    if outcome.refused:
        return JSONResponse(status_code=HTTP_BAD_REQUEST, content=outcome.refusal.model_dump())

    assert outcome.report is not None
    if output_format == "csv":
        return PlainTextResponse(
            to_csv(outcome.report, settings.model),
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="{outcome.report.submission_id}-completeness.csv"'
                )
            },
        )
    return to_dict(outcome.report, settings.model)
