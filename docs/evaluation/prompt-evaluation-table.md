# Prompt Evaluation Table

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v1.0-per-item`  
Cases run: 2  
Cases meeting expectation: 2 of 2

| Case | AC | Scenario | Expected | Actual | Result | Seconds |
|---|---|---|---|---|---|---|
| EV-12 | AC2 | User uploads an unsupported file type as the submission. | Clear error naming the supported formats; analysis does not run | Rejected with a clear error: Unsupported file type '.xlsx'. Supported types: .pdf, .txt, .md, .docx. | Pass | 0.0 |
| EV-13 | AC7 | Caller supplies two submissions for comparison. | Rejected before analysis; no comparative output is possible | Rejected before analysis: This system processes one submission at a time and cannot compare or rank submissions. Please upload a single submission. | Pass | 0.0 |
