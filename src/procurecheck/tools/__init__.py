"""Tools and tool calling (Week 4).

contracts      the schemas from the Tool / Function Specification
authorization  who may call which tool
completeness   check_document_completeness and generate_completeness_report
registry       the registry, and the executor every call passes through
orchestrator   the model proposes calls; the application runs them
"""

from .authorization import Principal
from .completeness import TOOL_CHECK, TOOL_REPORT, ToolContext
from .contracts import ErrorCode, ToolError
from .orchestrator import AgentRun, AgentSession, ToolCallingAgent
from .registry import ToolExecutor, ToolRegistry, ToolResult, ToolSpec, default_registry

__all__ = [
    "AgentRun",
    "AgentSession",
    "ErrorCode",
    "Principal",
    "TOOL_CHECK",
    "TOOL_REPORT",
    "ToolCallingAgent",
    "ToolContext",
    "ToolError",
    "ToolExecutor",
    "ToolRegistry",
    "ToolResult",
    "ToolSpec",
    "default_registry",
]
