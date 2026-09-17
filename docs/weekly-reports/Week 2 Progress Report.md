# Week 2 Progress Report

**ProcureCheck: Public Procurement Document-Completeness Agent.** BSE4104, Group H (Evening), Makerere University. Week 2, 11 to 16 September 2026.

## 1. Objective and Work Completed

Week 2 aimed to build a working model-backed baseline and test it before retrieval was added. All five tasks were completed, as Table 1 shows.

<!-- Table: Week 2 tasks, owners and evidence -->
| Task | Owners | Evidence |
| --- | --- | --- |
| Choose and document an accessible model | Isaac Mwesigwa | Accessible Model Documentation |
| Integrate the model into the application | Jonathan Katongole | Application code in src/procurecheck/ |
| Prompt Specification v1.0 | Jonathan Katongole, Makmot Johnson | Prompt Specification v1.0 and v2.0 |
| At least two prompt iterations | Makmot Johnson | Prompt Iteration Record, version history |
| At least 10 test cases, expected against actual | Bataringaya Bridget, Jonathan Katongole | Team test case and 19-case evaluations |

## 2. Model and Integration

Meta Llama 3.1 8B Instruct was selected for free local use, structured output and data control. Google Gemini 1.5 Flash was named as a long-document fallback but is not yet configured. The model runs through Ollama at temperature 0.0. Each request carries the output schema, so answers must match it. The context window was set to 16,384 tokens, because Ollama otherwise truncates at 4,096. A code-level guard refuses scoring, ranking, legal and award requests before any model call.

## 3. Prompt Iterations

Three versions were measured on the same 19 cases, as Table 2 shows.

<!-- Table: Prompt versions and measured results -->
| Version | Change | Cases met |
| --- | --- | --- |
| v1.0 | Baseline specification | 15 of 19 |
| v2.0 | Decision steps, absence as a normal answer, identity test | 17 of 19 |
| v2.1 | v2.0 plus a second call that checks each quotation without the submission | 19 of 19 |

Version 1.0 never reported a document as absent. Version 2.0 fixed this, but twice quoted real text from the wrong document. Version 2.1 rejected both, while keeping all four correct matches worded differently from the checklist.

## 4. Test Results

The team's ten cases met expectation in seven, as Table 3 shows.

<!-- Table: Team test case results by behaviour -->
| Behaviour tested | Cases | Met |
| --- | --- | --- |
| Checklist extraction, scoped analysis, clause matching | TC01 to TC03 | 3 of 3 |
| Missing item detection | TC04, TC05 | 0 of 2 |
| Refusal to score, rank, judge legality or recommend award | TC06 to TC09 | 4 of 4 |
| Ambiguous clause sent to human review | TC10 | 0 of 1 |

TC04 and TC05 both missed a signed bid form that was present; their missing items were detected correctly. TC10 reported an ambiguous clause Not Found instead of sending it to a person.

## 5. Limitations and Next Steps

Tests ran on a CPU-only machine at 91 to 432 seconds per item, on short synthetic submissions. Scanned documents were refused and checks were limited to about 45 pages. Week 3 will add retrieval over a controlled PPDA corpus, investigate the TC04 and TC05 miss, and route uncertain matches such as TC10 to human review.
