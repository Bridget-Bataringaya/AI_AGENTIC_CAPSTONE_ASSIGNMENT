# Evaluation of synthetic-submission-txt

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV-16 | AC2, AC3 | synthetic-submission-txt | Same submission content supplied as a plain .txt file. | Found, with page_number 1 and a verbatim snippet | synthetic-submission.txt: Found (confidence 0.95, no page) "A bid guarantee in the sum of UGX 24,000,000.00 has been issued in fav..." | Pass | 180.8 |
