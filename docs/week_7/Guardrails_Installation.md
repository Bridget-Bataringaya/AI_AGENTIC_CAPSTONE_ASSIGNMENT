# Week 7: Guardrails implementation

Task: Implement input/output validation, tool allow-list, authorization, agent iteration limits, approval controls and prompt-injection awareness.

ClickUp: https://app.clickup.com/t/123tcvwp3fn

## What this change implements

The existing ProcureCheck repository already contains request safety checks, a role-based permission model, bounded workflow iterations, approved tool definitions, and approval controls. This patch closes a gap by adding API-key and role-permission protection to the older `POST /check` and `POST /checklist/parse` endpoints.

- Missing or invalid API key: HTTP 401
- Authenticated role without `document:analyse`: HTTP 403
- Misconfigured API-key environment setting: fail closed, HTTP 500
- No changes to existing matching or document parsing business logic

## Test commands

From the repository root, install the project development dependencies, then run:

```bash
PYTHONPATH=src python -m pytest -v tests/test_legacy_auth.py tests/test_guardrail_contract.py
```

These tests are submitted as code and have **not** been verified as passing during this commit. Record actual test output and API responses as execution evidence.

## Important limitations

- Role-level permission does not imply document-level access control. The application requires case ownership checks before claiming document isolation.
- Prompt-injection instructions inside uploaded documents require adversarial evaluation; prompt wording is not sufficient proof of protection.
- Existing endpoint upload caps do not cover all potential decompression and document-parser resource risks.
- The ZIP's Python `__pycache__` and `.pyc` build outputs are intentionally excluded from version control.
