# Evaluation of synthetic-submission-docx

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Seconds |
|---|---|---|---|---|---|---|---|
| EV-15 | AC2, AC3 | synthetic-submission-docx | Same submission content supplied as a Word .docx file instead of a PDF. Word documents carry no reliable page boundaries without rendering, so the agent must report page 1 rather than invent a page number a reviewer could not verify. | Found, with page_number 1 and a verbatim snippet | synthetic-submission.docx: Found (confidence 0.95, no page) "The bidder encloses a Tax Clearance Certificate issued by the national..." | Pass | 178.6 |
