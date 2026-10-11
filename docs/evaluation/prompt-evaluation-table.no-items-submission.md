# Evaluation of no-items-submission

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v1.0-per-item`  
Cases run: 1  
Cases meeting expectation: 0 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV-18 | AC4 | no-items-submission | A complete, realistic tender package that contains NONE of the ten required documents: only a method statement, programme, plant schedule, personnel list and safety approach. Three unrelated checklist items are checked against it. This isolates whether the model can report absence at all, or only ever latches onto the nearest plausible text. | All three items Not Found, with no page number and no snippet | 0 of 3 Not Found. CHK-01=Requires Human Review (conf 0.00); CHK-02=Requires Human Review (conf 0.00); CHK-04=Requires Human Review (conf 0.00) | Fail | 399.7 |
