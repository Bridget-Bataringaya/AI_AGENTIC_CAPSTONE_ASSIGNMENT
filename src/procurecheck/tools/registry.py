"""The tool registry and the executor every tool call passes through.

Whether a call comes from the model, from the API or from a test, it is run by
ToolExecutor.execute and nothing else. That one method owns the order of the
checks, so no route into a tool can skip one:

1. the tool must exist,                        else UNKNOWN_TOOL
2. the caller must hold the tool's permission, else UNAUTHORIZED
3. the arguments must match the input schema,  else MISSING_PARAMETER or
                                                    INVALID_ARGUMENTS
4. the tool runs; a declared failure keeps its own code, a backend outage
   becomes SERVICE_UNAVAILABLE, anything else becomes the tool's own generic
   failure code (ANALYSIS_FAILED, REPORT_GENERATION_FAILED)
5. the answer must match the output schema,    else UNEXPECTED_TOOL_RESPONSE

Authorization runs before argument validation on purpose: a caller who may not
use a tool learns nothing about its parameters by probing it.
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Final, List, Mapping, Optional, Tuple, Type

from pydantic import BaseModel, ValidationError

from ..llm import ModelUnavailableError
from .authorization import PERMISSION_ANALYSE, PERMISSION_REPORT, Principal, is_permitted
from .completeness import (
    TOOL_CHECK,
    TOOL_REPORT,
    ToolContext,
    check_document_completeness,
    generate_completeness_report,
)
from .contracts import (
    CheckCompletenessInput,
    CheckCompletenessOutput,
    ErrorCode,
    GenerateReportInput,
    GenerateReportOutput,
    ToolError,
    ToolFailure,
)

MISSING_ERROR_TYPE: Final[str] = "missing"

logger = logging.getLogger(__name__)

Handler = Callable[[Any, ToolContext], BaseModel]


@dataclass(frozen=True)
class ToolSpec:
    """One tool: what it is for, what it takes and returns, and who may call it.

    `bound_fields` are arguments the application supplies from the session
    instead of the model, such as the document text. They are hidden from the
    schema the model sees, and whatever the model puts in them is discarded.
    A model that could write `document_text` could be steered by the document
    into checking a different document than the one uploaded.
    """

    name: str
    description: str
    input_model: Type[BaseModel]
    output_model: Type[BaseModel]
    permission: str
    handler: Handler
    failure_code: ErrorCode
    unauthorized_message: str
    bound_fields: Tuple[str, ...] = ()
    # The code for arguments that are present but malformed. The report tool
    # uses the specification's INVALID_RESULTS, since its arguments are results.
    invalid_arguments_code: ErrorCode = ErrorCode.INVALID_ARGUMENTS

    def model_parameters(self) -> Dict[str, Any]:
        """The input JSON schema with bound fields removed, for the model."""
        schema = copy.deepcopy(self.input_model.model_json_schema())
        properties = schema.get("properties", {})
        for name in self.bound_fields:
            properties.pop(name, None)
        schema["required"] = [r for r in schema.get("required", []) if r not in self.bound_fields]
        schema.pop("title", None)
        schema.pop("additionalProperties", None)
        if not properties:
            schema.pop("$defs", None)
        return schema

    def definition(self) -> Dict[str, Any]:
        """The tool as Ollama's /api/chat `tools` field expects it."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.model_parameters(),
            },
        }

    def describe(self) -> Dict[str, Any]:
        """The full contract, for GET /tools and documentation."""
        return {
            "name": self.name,
            "description": self.description,
            "permission": self.permission,
            "input_schema": self.input_model.model_json_schema(),
            "output_schema": self.output_model.model_json_schema(),
            "bound_by_application": list(self.bound_fields),
        }


@dataclass(frozen=True)
class ToolResult:
    """What one tool call produced, and enough about it to trace it later."""

    tool: str
    arguments: Mapping[str, Any]
    output: Optional[BaseModel] = None
    error: Optional[ToolError] = None
    duration_ms: int = 0

    @property
    def ok(self) -> bool:
        return self.error is None

    def payload(self) -> Dict[str, Any]:
        """The envelope returned to the caller: the success schema or the error."""
        if self.error is not None:
            return self.error.to_dict()
        assert self.output is not None
        return self.output.model_dump(mode="json")

    def to_trace(self) -> Dict[str, Any]:
        return {
            "tool": self.tool,
            "arguments": {k: _abbreviate(v) for k, v in self.arguments.items()},
            "status": "success" if self.ok else "error",
            "error_code": None if self.error is None else self.error.error_code.value,
            "duration_ms": self.duration_ms,
            "result": self.payload(),
        }


TRACE_TEXT_LIMIT: Final[int] = 200


def _abbreviate(value: Any) -> Any:
    """Keep traces readable: a whole submission is not repeated in every record."""
    if isinstance(value, str) and len(value) > TRACE_TEXT_LIMIT:
        return f"{value[:TRACE_TEXT_LIMIT]}... ({len(value)} characters)"
    return value


def _argument_error(spec: ToolSpec, exc: ValidationError) -> ToolError:
    errors = exc.errors()
    missing = [".".join(str(p) for p in e["loc"]) for e in errors if e["type"] == MISSING_ERROR_TYPE]
    if missing:
        return ToolError(
            error_code=ErrorCode.MISSING_PARAMETER,
            message=f"{spec.name} is missing required parameter(s): {', '.join(missing)}.",
        )
    detail = "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or 'arguments'}: {e['msg']}" for e in errors[:3]
    )
    return ToolError(
        error_code=spec.invalid_arguments_code,
        message=f"{spec.name} received invalid arguments. {detail}.",
    )


@dataclass
class ToolRegistry:
    specs: Dict[str, ToolSpec] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self.specs:
            raise ValueError(f"tool {spec.name!r} is already registered")
        self.specs[spec.name] = spec

    def get(self, name: str) -> Optional[ToolSpec]:
        return self.specs.get(name)

    def definitions(self) -> List[Dict[str, Any]]:
        return [spec.definition() for spec in self.specs.values()]

    def names(self) -> List[str]:
        return list(self.specs)


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, context: ToolContext) -> None:
        self._registry = registry
        self._context = context

    @property
    def registry(self) -> ToolRegistry:
        return self._registry

    def execute(
        self, name: str, arguments: Mapping[str, Any], principal: Optional[Principal]
    ) -> ToolResult:
        started = time.perf_counter()

        def finish(output: Optional[BaseModel] = None, error: Optional[ToolError] = None) -> ToolResult:
            elapsed = int((time.perf_counter() - started) * 1000)
            return ToolResult(name, dict(arguments), output, error, elapsed)

        spec = self._registry.get(name)
        if spec is None:
            return finish(error=ToolError(
                error_code=ErrorCode.UNKNOWN_TOOL,
                message=f"No tool named {name!r}. Available: {', '.join(self._registry.names())}.",
            ))
        if not is_permitted(principal, spec.permission):
            return finish(error=ToolError(
                error_code=ErrorCode.UNAUTHORIZED, message=spec.unauthorized_message
            ))
        try:
            args = spec.input_model.model_validate(dict(arguments))
        except ValidationError as exc:
            return finish(error=_argument_error(spec, exc))

        try:
            raw = spec.handler(args, self._context)
        except ToolFailure as failure:
            return finish(error=failure.to_error())
        except ModelUnavailableError as exc:
            return finish(error=ToolError(
                error_code=ErrorCode.SERVICE_UNAVAILABLE,
                message=f"The model backend is unavailable, so {name} could not run. {exc}",
            ))
        except Exception as exc:  # noqa: BLE001 - any other fault must not escape as a crash
            # The exception text can carry internals (paths, document text), so
            # the caller gets its type and the server log gets the rest.
            logger.exception("Tool %s failed unexpectedly", name)
            return finish(error=ToolError(
                error_code=spec.failure_code,
                message=f"{name} failed unexpectedly ({type(exc).__name__}). Please try again.",
            ))

        try:
            output = spec.output_model.model_validate(
                raw.model_dump() if isinstance(raw, BaseModel) else raw
            )
        except ValidationError as exc:
            return finish(error=ToolError(
                error_code=ErrorCode.UNEXPECTED_TOOL_RESPONSE,
                message=(
                    f"{name} returned a response that does not match its output schema, "
                    f"so it was discarded. {exc.error_count()} problem(s), first: "
                    f"{exc.errors()[0]['msg']}."
                ),
            ))
        return finish(output=output)


def default_registry() -> ToolRegistry:
    """The two tools from the Tool / Function Specification."""
    registry = ToolRegistry()
    registry.register(ToolSpec(
        name=TOOL_CHECK,
        description=(
            "Check the uploaded procurement document against its checklist of "
            "required items. Returns Present, Missing or Unclear for each item "
            "and the completeness percentage. The application supplies the "
            "document text and the checklist; do not pass them."
        ),
        input_model=CheckCompletenessInput,
        output_model=CheckCompletenessOutput,
        permission=PERMISSION_ANALYSE,
        handler=check_document_completeness,
        failure_code=ErrorCode.ANALYSIS_FAILED,
        unauthorized_message="You do not have permission to analyse this procurement document.",
        bound_fields=("document_text", "required_items"),
    ))
    registry.register(ToolSpec(
        name=TOOL_REPORT,
        description=(
            "Turn the latest completeness results into a structured report with "
            "present, missing and unclear items and recommendations. Call it "
            "after check_document_completeness has succeeded. It takes no arguments."
        ),
        input_model=GenerateReportInput,
        output_model=GenerateReportOutput,
        permission=PERMISSION_REPORT,
        handler=generate_completeness_report,
        failure_code=ErrorCode.REPORT_GENERATION_FAILED,
        unauthorized_message="You do not have permission to generate or access this report.",
        bound_fields=(
            "document_name", "document_type", "completeness_percentage", "completeness_results",
        ),
        invalid_arguments_code=ErrorCode.INVALID_RESULTS,
    ))
    return registry
