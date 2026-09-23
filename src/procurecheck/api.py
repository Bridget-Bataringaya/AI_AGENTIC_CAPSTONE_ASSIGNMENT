"""FastAPI backend.

The API / Backend Service from the Architecture and Context Diagram (Sec. 4).
It orchestrates ingestion, the Safety Guard, the Matching Engine and the Report
Generator for a single in-progress completeness check.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Body, Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
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
from .tools import (
    AgentSession,
    ErrorCode,
    Principal,
    ToolCallingAgent,
    ToolContext,
    ToolError,
    ToolExecutor,
    default_registry,
)
from .tools.authorization import ApiKeyError, load_api_keys, principal_for_key

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAUTHENTICATED = 401
HTTP_FORBIDDEN = 403
HTTP_NOT_FOUND = 404
HTTP_UNPROCESSABLE = 422
HTTP_SERVER_ERROR = 500
HTTP_BAD_GATEWAY = 502
HTTP_SERVICE_UNAVAILABLE = 503

# How each tool error surfaces over HTTP. The body is always the
# specification's error envelope; the status code only tells a client which
# kind of failure to handle without parsing it.
TOOL_ERROR_STATUS: Dict[ErrorCode, int] = {
    ErrorCode.UNAUTHORIZED: HTTP_FORBIDDEN,
    ErrorCode.UNKNOWN_TOOL: HTTP_NOT_FOUND,
    ErrorCode.MISSING_PARAMETER: HTTP_UNPROCESSABLE,
    ErrorCode.INVALID_ARGUMENTS: HTTP_UNPROCESSABLE,
    ErrorCode.EMPTY_DOCUMENT: HTTP_UNPROCESSABLE,
    ErrorCode.UNSUPPORTED_DOCUMENT: HTTP_UNPROCESSABLE,
    ErrorCode.MISSING_CHECKLIST: HTTP_UNPROCESSABLE,
    ErrorCode.NO_ANALYSIS_RESULTS: HTTP_UNPROCESSABLE,
    ErrorCode.INVALID_RESULTS: HTTP_UNPROCESSABLE,
    ErrorCode.REFUSED: HTTP_BAD_REQUEST,
    ErrorCode.SERVICE_UNAVAILABLE: HTTP_SERVICE_UNAVAILABLE,
    ErrorCode.UNEXPECTED_TOOL_RESPONSE: HTTP_BAD_GATEWAY,
    ErrorCode.STEP_LIMIT_REACHED: HTTP_UNPROCESSABLE,
}

logger = logging.getLogger(__name__)

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


# Week 4: tools and tool calling. The /check route above predates
# authentication and is left unchanged; the routes below require an API key.


def get_principal(x_api_key: Optional[str] = Header(default=None)) -> Optional[Principal]:
    """The caller behind the X-API-Key header, or None if there is none.

    None is not rejected here. It is passed on so the executor refuses it with
    the specification's own UNAUTHORIZED envelope, the same one a model-driven
    call would get.
    """
    try:
        keys = load_api_keys()
    except ApiKeyError as exc:
        # The detail stays in the server log. The caller is unauthenticated at
        # this point and learns only that the server is misconfigured.
        logger.error("Tool routes refused: %s", exc)
        raise HTTPException(
            HTTP_SERVER_ERROR, "Server configuration error: the API keys are misconfigured."
        ) from exc
    return principal_for_key(x_api_key, keys)


def _error_response(error: ToolError, principal: Optional[Principal]) -> JSONResponse:
    status = TOOL_ERROR_STATUS.get(error.error_code, HTTP_SERVER_ERROR)
    if error.error_code is ErrorCode.UNAUTHORIZED and principal is None:
        status = HTTP_UNAUTHENTICATED
    return JSONResponse(status_code=status, content=error.to_dict())


@app.get("/tools")
def list_tools() -> List[Dict[str, Any]]:
    """Each tool's purpose, input and output schema, and required permission."""
    return [spec.describe() for spec in default_registry().specs.values()]


@app.post("/tools/{name}")
def call_tool(
    name: str,
    arguments: Dict[str, Any] = Body(default_factory=dict),
    principal: Optional[Principal] = Depends(get_principal),
    settings: Settings = Depends(get_settings),
):
    """Call one tool directly, through the same executor the agent uses."""
    with OllamaClient(settings) as client:
        executor = ToolExecutor(default_registry(), ToolContext(settings, client))
        result = executor.execute(name, arguments, principal)
    if not result.ok:
        return _error_response(result.error, principal)
    return result.payload()


@app.post("/agent")
def run_agent(
    submission: UploadFile = File(..., description="One tender submission"),
    checklist: Optional[UploadFile] = File(default=None, description="Checklist; bundled standard if omitted"),
    request: str = Form(default="Check this document for completeness and give me the report."),
    principal: Optional[Principal] = Depends(get_principal),
    settings: Settings = Depends(get_settings),
):
    """Let the model choose and call the tools on one submission.

    Returns the full trace: every call the model proposed, what the executor
    did with it, and the final answer.
    """
    from . import checklists

    with tempfile.TemporaryDirectory() as workspace:
        directory = Path(workspace)
        submission_path = _save_upload(submission, directory)
        checklist_path = (
            _save_upload(checklist, directory) if checklist else checklists.resolve(checklists.STANDARD)[0]
        )
        try:
            items = parse_checklist(checklist_path)
            parsed = parse_submission(submission_path)
        except (UnsupportedDocumentError, EmptyChecklistError, EmptyDocumentError) as exc:
            raise HTTPException(HTTP_BAD_REQUEST, str(exc)) from exc

    session = AgentSession(
        document_name=submission_path.name,
        document_text=parsed.as_marked_text(),
        required_items=tuple(item.description for item in items),
    )
    with OllamaClient(settings) as client:
        executor = ToolExecutor(default_registry(), ToolContext(settings, client))
        run = ToolCallingAgent(client, executor).run(request, principal, session)
    trace = run.to_trace()
    if run.error is not None:
        status = TOOL_ERROR_STATUS.get(run.error.error_code, HTTP_SERVER_ERROR)
        if run.error.error_code is ErrorCode.UNAUTHORIZED and principal is None:
            status = HTTP_UNAUTHENTICATED
        return JSONResponse(status_code=status, content=trace)
    return trace
