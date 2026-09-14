# Evaluation of long-submission-pdf

Public Procurement Document-Completeness Agent, Week 2 baseline.

Model: `llama3.1:8b`  
Prompt version: `v2.0-per-item`  
Cases run: 1  
Cases meeting expectation: 1 of 1

| Case | AC | Document | Scenario | Expected | Actual | Result | Seconds |
| --- | --- | --- | --- | --- | --- | --- | --- |
| EV-19 | Prompt Spec v1.0 Sec. 7 | long-submission-pdf | A 60-page submission, larger than the configured 16,384-token context window. Silent truncation here would report present documents as missing, so the request must be refused instead. | Refused before any model call, with an error naming the token budget and the configured window | Refused a 60-page submission before any model call: Checklist plus submission is roughly 21,267 tokens, above the 12,336 token budget of the configured context window (16,384 tokens). Raise PROCURECHECK_CONTEXT_TOKENS if the machine has the memory, or route to the Google Gemini 1.5 Flash fallback described in Prompt Specification v1.0 Sec. 7, which is not yet configured. | Pass | 0.2 |
