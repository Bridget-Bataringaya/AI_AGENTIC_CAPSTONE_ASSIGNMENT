# Bridget Bataringaya — Individual Task Evidence Index

This index records **Bridget's individually assigned work**, plus explicitly labelled shared assignments, as of 12 October 2026. It does **not** claim that the linked ClickUp attachments are stored in GitHub. Source documents remain attached to ClickUp until their exact binary files are transferred and independently verified.

**Branch policy:** All Bridget-specific work belongs on `Bridget-Bataringaya`, never directly on `main`.

## Individually assigned tasks

| Week | Task | Source evidence in ClickUp | GitHub status |
|---|---|---|---|
| 1 | [Create 2–3 Page Project Charter](https://app.clickup.com/t/123tcvwcfk7) | `Project Charter.docx` attached | ClickUp evidence only; document not copied to GitHub |
| 1 | [Set Up GitHub Repository and ClickUp Evidence](https://app.clickup.com/t/123tcvwcfkd) | Completed task; repository exists | Existing repo; no separate deliverable file identified |
| 2 | [Create at least 10 test cases and record expected vs actual behaviour](https://app.clickup.com/t/123tcvwd9up) | `Prompt Evaluation Table.docx`; `Team Test Case Evaluation.docx` attached | ClickUp evidence only |
| 3 | [Assemble a controlled corpus and record provenance](https://app.clickup.com/t/123tcvwe2y4) | `CORPUS_GROUP_H.zip` attached (approx. 40.7 MB) | ClickUp evidence only; corpus not copied or inspected here |
| 4 | [Define at least two tools/functions including schemas and authorization](https://app.clickup.com/t/123tcvwfnx8) | `Public_Procurement_Agent_Tool_Function_Specification..docx` attached | ClickUp evidence only |
| 5 | [Design Sense/Context → Plan/Decide → Act/Tool → Observe → Stop/Re-plan](https://app.clickup.com/t/123tcvwhmc7) | `Public_Procurement_Document_Completeness_Agent_Workflow.pdf` attached | ClickUp evidence only |
| 6 | [Document an MCP-style interface](https://app.clickup.com/t/123tcvwkyw2) | `Public_Procurement_MCP_Style_Interface.pdf` attached | ClickUp evidence only |
| 7 | [Implement guardrails](https://app.clickup.com/t/123tcvwp3fn) | ZIP supplied through ChatGPT; GitHub evidence comment posted to ClickUp | **Code committed** below; tests not verified as passing |

### Week 7 guardrails files

- [`src/procurecheck/legacy_auth_patch.py`](../../src/procurecheck/legacy_auth_patch.py)
- [`src/procurecheck/api.py`](../../src/procurecheck/api.py) — modified for the patch
- [`tests/test_legacy_auth.py`](../../tests/test_legacy_auth.py)
- [`tests/test_guardrail_contract.py`](../../tests/test_guardrail_contract.py)
- [`docs/week_7/Guardrails_Installation.md`](../week_7/Guardrails_Installation.md)

The guardrails ZIP's binary PDF evidence is not yet committed to GitHub. The code was pushed to this personal branch, but successful automated execution has not been demonstrated.

## Shared assignments — do not represent as solely Bridget's

| Week | Task | ClickUp source | Status |
|---|---|---|---|
| 2 | [Week 2 progress report](https://app.clickup.com/t/123tcvwd9v7) | `Week 2 Progress Report` attached | Shared with Isaac; avoid duplicating or claiming exclusive authorship |
| 3 | [Three retrieval/grounding failures](https://app.clickup.com/t/123tcvwe2yj) | `Public Procurement Completeness Agent - Retrieval & Grounding Failure Analysis.docx` attached | Shared with Isaac |
| 4 | [Week four report](https://app.clickup.com/t/123tcvwfnzj) | `Week 4 Progress Report` attached; task refers to Jonathan's branch | Shared with Isaac; do not copy teammate-authored work |
| 5 | [Iteration limits and human hand-off/approval conditions](https://app.clickup.com/t/123tcvwhmca) | `Agent_Task_Contract_Public_Procurement_Document_Completeness_Agent.docx` attached | Shared with Isaac |
| 6 | [Demonstrate memory's legitimate value](https://app.clickup.com/t/123tcvwkyvu) | No attachment; ClickUp status **to do** | Shared with Isaac; evidence and completion still required |
| 7 | [Define evaluation criteria and scoring rubric](https://app.clickup.com/t/123tcvwp3fj) | `Evaluation_Criteria_and_Scoring_Rubric.pdf` attached | Shared with Isaac |

## Verification and next steps

1. Keep the original ClickUp files and use their task links as provenance.
2. Transfer the **exact source attachments** from ClickUp to this branch when binary upload is available; do not replace originals with newly invented content.
3. For shared assignments, check the individual's contribution before committing or claiming authorship.
4. Run tests and record actual outputs for the guardrails implementation; currently **not verified**.
5. When evidence files are added, update this table with their precise GitHub paths and commit references.
