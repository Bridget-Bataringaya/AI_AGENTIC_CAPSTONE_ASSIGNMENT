# Prompt Evaluation Table

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v1.0-per-item`  
Cases run: 2  
Cases meeting expectation: 1 of 2

| Case | AC | Scenario | Expected | Actual | Result | Seconds |
| --- | --- | --- | --- | --- | --- | --- |
| TG-01 | AC3, AC4 | CHK-02 was expected to be present in synthetic-submission.pdf. | Found, with a page number and a verbatim snippet | synthetic-submission.pdf: Found (confidence 1.00, page 3) "The bidder encloses a Tax Clearance Certificate issued by the national..." | Pass | 234.2 |
| TG-02 | AC3, AC4 | CHK-05 was expected to be absent in synthetic-submission.pdf. | Not Found, with no page number and no snippet | synthetic-submission.pdf: Found (confidence 1.00, page 7) "The bidder confirms that no director, officer or shareholder of Kavuma..." | Fail | 194.8 |
