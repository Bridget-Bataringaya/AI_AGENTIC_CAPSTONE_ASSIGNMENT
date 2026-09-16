# Prompt Evaluation Report

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v1.0-per-item`  
Cases run: 2  
Cases meeting expectation: 1 of 2

| Case | AC | Document | Scenario | Expected | Actual | Result | Observation | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TG-01 | AC3, AC4 | none | CHK-02 was expected to be present in synthetic-submission.pdf. | Found, with a page number and a verbatim snippet | synthetic-submission.pdf: Found, confidence 1.00. The model was given the submission and located the document on page 3. The quotation was confirmed to appear in the submission. Final confidence was 1.00, at or above the 0.85 review threshold. Evidence: Page 3: "The bidder encloses a Tax Clearance Certificate issued by the national revenue authority, reference TCC/2026/00417, valid from 01 January 2026 to 31 December 2026. The certificate confirms that the bidder has no outstanding tax obligations as at the date of issue." | Pass | Expected Found. The system returned Found. The outcome matched the expectation. | 234.2 |
| TG-02 | AC3, AC4 | none | CHK-05 was expected to be absent in synthetic-submission.pdf. | Not Found, with no page number and no snippet | synthetic-submission.pdf: Found, confidence 1.00. The model was given the submission and located the document on page 7. The quotation was confirmed to appear in the submission. Final confidence was 1.00, at or above the 0.85 review threshold. Evidence: Page 7: "The bidder confirms that no director, officer or shareholder of Kavuma Civil Works Limited holds any interest, direct or indirect, in the Procuring Entity, and that no circumstance exists that would place the bidder in a position of conflict in respect of this procurement. Signed by the Managing..." | Fail | Expected Not Found. The system returned Found. A missing document was reported present on page 7. This is the most serious error the system can make, because it hides a gap in the bid. | 194.8 |
