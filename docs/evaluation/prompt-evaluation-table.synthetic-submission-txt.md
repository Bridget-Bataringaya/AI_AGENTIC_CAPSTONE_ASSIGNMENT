# Evaluation of synthetic-submission-txt

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item + adjudicator-v1.0`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Observation | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EV-16 | AC2, AC3 | synthetic-submission-txt | Same submission content supplied as a plain .txt file. | Found, with page_number 1 and a verbatim snippet | synthetic-submission.txt: Found, confidence 0.89. The model was given the single page of the submission and located the document in the submission. The file format has no page boundaries, so no page was given. The quotation was confirmed to appear in the submission. The evidence check then compared the quotation with the requirement. It described the quoted passage as "Bid guarantee" and the requirement as "Bid security". It judged them to be the same document. Final confidence was 0.89, at or above the 0.85 review threshold. Evidence: No page number, as the file format has no pages: "A bid guarantee in the sum of UGX 24,000,000.00 has been issued in favour of the Procuring Entity by Synthetic Commercial Bank Limited, guarantee number BG/2026/0221, valid for one hundred and twenty (120) days from the bid submission deadline, in the form prescribed in the bidding document." | Pass | Expected Found. The system returned Found. The outcome matched the expectation. | 216.6 |
