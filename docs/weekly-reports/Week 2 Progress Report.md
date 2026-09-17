---
title: Week 2 Progress Report
subtitle: Model Baseline, Prompt Specification and Test Case Evaluation
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: School of Computing and Informatics Technology, Makerere University
line: Reporting period: 11 to 16 September 2026
---

# Declaration

The members of Group H (Evening) declare that this report is their own work. It has not been submitted for any other course or award. Work by other authors has been cited where it was used.

- Jonathan Katongole
- Makmot Johnson
- Isaac Mwesigwa
- Bataringaya Bridget

# Dedication

This report is dedicated to the procurement officers whose careful checking this project aims to support.

# Acknowledgement

The group thanks the BSE4104 course lecturer for the weekly structure and the document format that guided this work. Isaac Mwesigwa is thanked for the model selection study that fixed the model and its settings. Makmot Johnson is thanked for the prompt iteration record that first predicted the missing-item failure. Bataringaya Bridget is thanked for writing the ten test cases before the model was integrated. Jonathan Katongole is thanked for integrating the model and running the evaluations.

[[TOC]]

[[TABLES]]

[[FIGURES]]

# Abstract

**Introduction.** Week 2 aimed to build a working model-backed baseline for checking tender submissions for completeness. **Methods.** Meta Llama 3.1 8B Instruct was selected and run locally through Ollama with schema-constrained output. A prompt specification was written, and three prompt versions were built. Each version was tested on 19 built-in cases. The team's ten test cases were then run on the final version. **Results.** Cases meeting expectation rose from 15 of 19 to 19 of 19 across the three versions. Seven of the team's ten cases met expectation. All four safety refusals held. Two cases missed a document that was present, and one ambiguous clause was not escalated for human review. **Conclusion.** The baseline reported absent documents correctly and kept its safety boundary. It still missed some present documents and did not escalate uncertain matches reliably.

# 1. Introduction and Objectives

ProcureCheck checks a tender submission against a procurement checklist. It reports which required documents are present, missing or in need of human review. It never scores, ranks or recommends an award. The Week 1 work defined the users, the scope and this safety boundary.

Week 2 moved the project from design to a working system. The weekly focus was to build the smallest useful model-backed capability. A tested baseline was required before retrieval or agents were added.

The objectives for Week 2 were:

1. To select an accessible language model and document its capability, cost, latency, privacy and access.
2. To integrate the selected model into the application as a working baseline.
3. To specify the prompt's role, task, context, constraints, output format and failure behaviour.
4. To compare at least two meaningful prompt iterations.
5. To verify system behaviour against at least ten test cases, recording expected against actual behaviour.

# 2. Background

Public procurement in Uganda is governed by the Public Procurement and Disposal of Public Assets Act, Cap. 205. Bids first pass a preliminary examination for required documents. This stage is a matching exercise between a checklist and the documents a bidder filed (PPDA, 2023).

A large language model can match a requirement to differently worded text. For example, it can accept "audited accounts" for "audited financial statements". It can also produce confident but wrong answers. Two properties therefore mattered for this work.

The first property is structured output. A model can be constrained to a fixed JSON schema during generation (Ollama, 2026). Every answer then carries the same fields: status, page number, quotation and confidence.

The second property is the reliability of stated confidence. Kadavath et al. (2022) found large models well calibrated on carefully formatted multiple-choice questions. Whether a small model's self-reported confidence can be trusted was not known in advance. It had to be measured.

Llama 3.1 was released in 8, 70 and 405 billion parameter sizes (Dubey et al., 2024). Every size accepts 128,000 tokens of context. The 8 billion parameter version runs on a laptop.

# 3. Methodology and Procedure

## 3.1 Model Selection

Four candidate models were compared on access cost, context window, structured output, refusal behaviour and local deployment (Mwesigwa, 2026). Meta Llama 3.1 8B Instruct was selected as the primary model. Google Gemini 1.5 Flash was named as a cloud fallback for documents beyond the local context window. The fallback was not configured during Week 2.

The model was run through Ollama with 4-bit quantisation, a download of 4.9 GB. Generation settings were fixed by the selection study. Table 1 lists them.

<!-- Table: Generation settings used in every run -->
| Setting | Value | Purpose |
| --- | --- | --- |
| Temperature | 0.0 | Repeatable answers |
| Top-p | 0.9 | Restricts sampling to likely tokens |
| Maximum output tokens | 2,048 | Structured answers only |
| Context window | 16,384 tokens | About 45 pages of submission |
| Human review threshold | 0.85 | Lower confidence is routed to a person |

## 3.2 Integration

The application sent each request to Ollama's chat endpoint with the output schema attached. The selection study had proposed the Pydantic AI library. Its sample code did not run, so the schema was passed to Ollama directly.

A safety guard was placed in code, ahead of the model. It refused requests to score, rank, judge legality or recommend an award. Refused requests never reached the model.

Three checks were applied to every model answer. The quotation had to appear in the submission. The page number had to exist. A match below the review threshold was routed to human review.

## 3.3 Prompt Specification and Iterations

Prompt Specification v1.0 fixed the role, task, context, constraints, output format and failure behaviour (Katongole and Johnson, 2026). Version 1.0 was run first to set a baseline. Each later version was written in response to measured failures (Johnson, 2026; Katongole, 2026).

Version 2.0 added ordered decision steps and stated absence as a normal answer. It also added an identity test separating a required document from a related one. Version 2.1 kept version 2.0 and added a second model call. That call received only the requirement and the quoted passage, never the submission.

## 3.4 Test Data and Procedure

Two sets of test cases were used. The built-in set held 19 cases. Most ran against a synthetic seven-page submission. Seven checklist items were present in it, often under different wording. Three were deliberately omitted. Other cases covered refusals, unsupported files, two submissions at once and prompt injection. The rest covered scanned files, a 60-page file and a submission with no required document.

The second set held the team's ten test cases (Bataringaya, 2026). Each case supplied its own checklist, submission and request. The expected behaviour was written before the model was integrated and was not edited after any run.

A case met expectation only when every checklist item returned its expected status. Each status was Found, Not Found or Requires Human Review. Confidence was a unitless score from 0.00 to 1.00. Time was measured in seconds per case.

All runs used the same CPU-only laptop.

## 3.5 Problems Encountered

Four problems arose and were resolved.

Ollama read only 4,096 tokens by default and silently discarded the rest. The window was set explicitly to 16,384 tokens.

The first model call of a run exceeded the 300-second request timeout. The timeout was raised to 1,800 seconds.

One test case asserted two behaviours at once, so a known failure hid a working defence. The case was split.

A quick run without the model overwrote the full results table. The two outputs were separated.

# 4. Results

The final prompt version met all 19 built-in cases. The team's test cases met expectation in seven of ten. Table 2 compares the three prompt versions on the built-in cases.

<!-- Table: Built-in evaluation results by prompt version -->
| Measure | v1.0 | v2.0 | v2.1 |
| --- | --- | --- | --- |
| Cases meeting expectation | 15 of 19 | 17 of 19 | 19 of 19 |
| Absent documents reported absent | 0 of 6 | 4 of 6 | 6 of 6 |
| Safety and injection cases passed | 5 of 5 | 5 of 5 | 5 of 5 |
| Failed cases | EV-05, EV-06, EV-07, EV-18 | EV-05, EV-07 | None |

Version 1.0 never returned Not Found in any of the 19 cases. It reported an absent anti-bribery declaration as Found at confidence 1.00. The quoted text was a real conflict of interest declaration.

Version 2.0 reported absence correctly for four of six absent documents. Two wrong-document answers remained. A registration certificate was offered as a non-blacklisting certificate at confidence 0.95.

Version 2.1 rejected both wrong-document answers. It kept all four correct matches worded differently from the checklist. One of those matches fell from confidence 0.95 to 0.89, still above the threshold.

Table 3 groups the team's ten test cases by the behaviour tested.

<!-- Table: Team test case results by behaviour tested -->
| Behaviour tested | Cases | Met |
| --- | --- | --- |
| Checklist extraction and scoped analysis | TC01, TC02 | 2 of 2 |
| Present clause matched with evidence | TC03 | 1 of 1 |
| Missing item detected | TC04, TC05 | 0 of 2 |
| Refusal to score, rank, judge legality or recommend award | TC06 to TC09 | 4 of 4 |
| Ambiguous clause escalated to human review | TC10 | 0 of 1 |

TC04 and TC05 failed on the same item. A signed bid form was present but reported Not Found. The missing items in both cases were detected correctly. TC10 reported an ambiguous insurance clause as Not Found instead of escalating it.

Every refusal was made in under 0.1 seconds, with no model call. Items that needed the model took between 91 and 432 seconds each. Timings varied more with other load on the machine than with the prompt version.

# 5. Discussion

Version 1.0 over-reported presence because it was asked to search. A search of a real submission always returns a nearest match. The model quoted that match rather than report nothing.

The quotation check could not catch this error. Each wrong quotation was real text from the submission. The confidence threshold could not catch it either, because wrong answers carried confidence of 0.95 and above. This departs from the good calibration reported by Kadavath et al. (2022). That study measured much larger models answering formatted questions, not a small model stating its confidence as text.

Version 2.1 worked by changing the question. The second call saw only two document names and one passage. It had nothing to search and no earlier answer to defend. Zheng et al. (2023) found that models can judge answers well but favour answers of their own kind. Here the same model judged its own output, so a shared blind spot would not be caught.

The TC04 and TC05 miss has a likely cause. That submission listed "Signed Bid Form" as a bare line, not as a described document. Version 2.0 asks for evidence that a document itself is present. A bare name may not have met that test. This explanation was not verified during Week 2.

TC10 exposed a gap in the code rather than in the prompt. Human review was triggered only for items the model claimed present. The model reported the insurance clause absent at confidence 0.00, so no review was triggered.

# 6. Conclusion

A working model-backed baseline was built, specified and tested in Week 2. All five objectives were met.

The main lesson was that a completeness checker fails most dangerously by reporting missing documents as present. Neither quotation checks nor confidence thresholds prevented this. A separate judging call with the submission withheld did.

The baseline's strengths were its safety boundary, evidence for every Found item and correct reporting of absence. Its weaknesses were missed present documents, weak escalation of uncertain items and slow CPU-only runs. All test data was short and synthetic, so results on real tender packs remain unknown.

The baseline can already support a procurement officer as a first pass. Every result still needs human confirmation.

# 7. Recommendations

- Retrieval should be added, so each requirement is matched against cited passages from a controlled corpus.
- Uncertain absences, such as TC10, should also be routed to human review.
- The signed bid form miss in TC04 and TC05 should be tested with described and bare document names.
- The evidence check should be tried with a second, different model.
- The Gemini fallback should be configured before submissions longer than 45 pages are tested.
- Real, anonymised tender packs should replace synthetic submissions in later testing.

# References

Bataringaya, B. (2026). *Public Procurement Agent: 10 test cases* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Dubey, A., et al. (2024). *The Llama 3 herd of models* (arXiv:2407.21783). arXiv. https://arxiv.org/abs/2407.21783

Johnson, M. (2026). *ProcureCheck Week 2 prompt specification and version iteration record* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Kadavath, S., et al. (2022). *Language models (mostly) know what they know* (arXiv:2207.05221). arXiv. https://arxiv.org/abs/2207.05221

Katongole, J. (2026). *Prompt version history* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Katongole, J., and Johnson, M. (2026). *Prompt Specification v1.0* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Mwesigwa, I. (2026). *Accessible model selection and technical documentation* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Ollama. (2026). *Ollama API documentation: Structured outputs*. https://github.com/ollama/ollama/blob/main/docs/api.md

Public Procurement and Disposal of Public Assets Authority. (2023). *The Public Procurement and Disposal of Public Assets (Rules and Methods for Procurement of Supplies, Works and Non-Consultancy Services) Regulations, 2023*. Kampala, Uganda.

Zheng, L., et al. (2023). *Judging LLM-as-a-judge with MT-Bench and Chatbot Arena* (arXiv:2306.05685). arXiv. https://arxiv.org/abs/2306.05685
