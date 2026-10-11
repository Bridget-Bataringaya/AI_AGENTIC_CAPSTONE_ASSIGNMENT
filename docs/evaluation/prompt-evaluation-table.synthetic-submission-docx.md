# Evaluation of synthetic-submission-docx

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item + adjudicator-v1.0`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Observation | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EV-15 | AC2, AC3 | synthetic-submission-docx | Same submission content supplied as a Word .docx file instead of a PDF. Word documents carry no reliable page boundaries without rendering, so the agent must report page 1 rather than invent a page number a reviewer could not verify. | Found, with page_number 1 and a verbatim snippet | synthetic-submission.docx: Found, confidence 0.95. The model was given the single page of the submission and located the document in the submission. The file format has no page boundaries, so no page was given. The quotation was confirmed to appear in the submission. The evidence check then compared the quotation with the requirement. It described the quoted passage as "Tax Clearance Certificate" and the requirement as "Tax Clearance Certificate". It judged them to be the same document. Final confidence was 0.95, at or above the 0.85 review threshold. Evidence: No page number, as the file format has no pages: "The bidder encloses a Tax Clearance Certificate issued by the national revenue authority, reference TCC/2026/00417, valid from 01 January 2026 to 31 December 2026. The certificate confirms that the bidder has no outstanding tax obligations as at the date of issue." | Pass | Expected Found. The system returned Found. The outcome matched the expectation. | 241.2 |
