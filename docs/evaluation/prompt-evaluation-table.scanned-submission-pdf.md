# Evaluation of scanned-submission-pdf

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item + adjudicator-v1.0`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Observation | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| EV-17 | AC2, Charter document-quality constraint | scanned-submission-pdf | A scanned, image-only PDF with no text layer, which the Project Charter names as a document-quality risk. The Architecture and Context Diagram promises an OCR fallback; it does not exist yet, so this case records the real behaviour. | Rejected with a clear error telling the user OCR is needed. It must fail loudly, never silently report every item as missing. | Rejected with a clear error: scanned-submission.pdf contains no extractable text. If it is a scanned document, it must be passed through OCR before it can be checked. | Pass | The actual behaviour above met every part of the expected behaviour. | 0.0 |
