"""Input and output contracts for the agent's tools.

Reproduces the schemas in the team's Tool / Function Specification
(Bataringaya, Week 4, ClickUp 123tcvwfnx8) field for field, so that the JSON a
caller sends and receives matches the document. Where the application needed
more than the document defines, the addition is marked below and is limited to
error codes: the success payloads are exactly as specified.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict, Field

STATUS_SUCCESS = "success"
STATUS_ERROR = "error"


class ItemPresence(str, Enum):
    """The three statuses the specification uses for one checklist item."""

    PRESENT = "Present"
    MISSING = "Missing"
    UNCLEAR = "Unclear"


class OverallStatus(str, Enum):
    COMPLETE = "Complete"
    INCOMPLETE = "Incomplete"
    NEEDS_REVIEW = "Needs Review"


class ErrorCode(str, Enum):
    """Every structured failure a tool call can end in.

    The first eight are named in the specification. The rest are raised by the
    orchestration layer rather than by a tool, for failures the specification
    could not name because they happen before or around the tool: a model that
    asks for a tool that does not exist, a call missing a parameter, a backend
    that is down, a tool that answers with something other than its schema.
    """

    UNAUTHORIZED = "UNAUTHORIZED"
    EMPTY_DOCUMENT = "EMPTY_DOCUMENT"
    UNSUPPORTED_DOCUMENT = "UNSUPPORTED_DOCUMENT"
    MISSING_CHECKLIST = "MISSING_CHECKLIST"
    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    NO_ANALYSIS_RESULTS = "NO_ANALYSIS_RESULTS"
    INVALID_RESULTS = "INVALID_RESULTS"
    REPORT_GENERATION_FAILED = "REPORT_GENERATION_FAILED"
    # Added by the orchestration layer.
    UNKNOWN_TOOL = "UNKNOWN_TOOL"
    MISSING_PARAMETER = "MISSING_PARAMETER"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    UNEXPECTED_TOOL_RESPONSE = "UNEXPECTED_TOOL_RESPONSE"
    STEP_LIMIT_REACHED = "STEP_LIMIT_REACHED"
    REFUSED = "REFUSED"


class ToolError(BaseModel):
    """The error envelope, as the specification writes it."""

    model_config = ConfigDict(frozen=True)

    status: Literal["error"] = STATUS_ERROR
    error_code: ErrorCode
    message: str

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")


class ToolFailure(Exception):
    """Raised inside a tool to end the call with a specific error code.

    A tool never returns a half-filled success payload to signal trouble. It
    raises this, and the executor turns it into a ToolError, so a caller can
    rely on `status` alone to know whether the rest of the payload is real.
    """

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_error(self) -> ToolError:
        return ToolError(error_code=self.code, message=self.message)


# Tool 1: check_document_completeness


class CheckCompletenessInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_text: str = Field(description="The extracted text of the procurement document")
    document_type: str = Field(description="The kind of document, e.g. Bid Document")
    required_items: List[str] = Field(
        description="The checklist of information the document is expected to contain"
    )


class ItemResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    item: str
    status: ItemPresence
    reason: str


class CheckCompletenessOutput(BaseModel):
    status: Literal["success"] = STATUS_SUCCESS
    document_type: str
    completeness_percentage: float = Field(ge=0.0, le=100.0)
    results: List[ItemResult]


# Tool 2: generate_completeness_report


class GenerateReportInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_name: str = Field(description="The name of the procurement document")
    document_type: str = Field(description="The kind of document, e.g. Bid Document")
    completeness_percentage: float = Field(
        description="The percentage calculated by check_document_completeness"
    )
    # Defaulted rather than required so that a call without results reaches the
    # tool and gets the specification's own NO_ANALYSIS_RESULTS, instead of a
    # generic missing-parameter error that says less about what to do next.
    completeness_results: List[ItemResult] = Field(
        default_factory=list,
        description="The per-item results returned by check_document_completeness",
    )


class ReportBody(BaseModel):
    document_name: str
    document_type: str
    overall_status: OverallStatus
    completeness_percentage: float = Field(ge=0.0, le=100.0)
    present_items: List[str]
    missing_items: List[str]
    unclear_items: List[str]
    recommendations: List[str]


class GenerateReportOutput(BaseModel):
    status: Literal["success"] = STATUS_SUCCESS
    report: ReportBody
