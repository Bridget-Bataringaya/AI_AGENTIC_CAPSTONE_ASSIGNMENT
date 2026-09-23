---
title: Week 3 Progress Report
subtitle: Controlled Corpus, Retrieval and Grounding
line: **Public Procurement Document-Completeness Agent (ProcureCheck)**
line: BSE4104 AI-Native and Agentic Engineering Capstone
line: Group H (Evening)
line: School of Computing and Informatics Technology, Makerere University
line: Reporting period: 16 to 22 September 2026
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

The group thanks the BSE4104 course lecturer for the weekly structure and the document format that guided this work. Bataringaya Bridget is thanked for assembling the controlled corpus of procurement documents. Isaac Mwesigwa is thanked for the context construction specification. Isaac Mwesigwa and Bataringaya Bridget are thanked for the retrieval failure analysis. Makmot Johnson is thanked for writing the sixteen RAG test questions. Jonathan Katongole is thanked for building the ingestion, indexing and search pipeline and running the evaluations.

[[TOC]]

[[TABLES]]

[[FIGURES]]

# Abstract

**Introduction.** Week 3 aimed to ground the completeness agent in a controlled body of procurement documents. **Methods.** A corpus of 35 documents was assembled with its provenance recorded. The documents were segmented under their headings, split into passages and indexed twice. One index matched keywords and the other matched meaning. Search combined both rankings. Retrieval was measured on 20 labelled queries. The team's 16 RAG test questions were then run through the safety guard and search. **Results.** Hybrid search placed the answering passage in the top 10 for 14 of 15 answerable queries. The safety guard refused both questions asking to rank bidders or recommend an award. Every other question cleared the evidence threshold, including three that had no answer. **Conclusion.** Retrieval found relevant passages reliably but could not tell when a question had no answer. Similarity alone was not a safe test of evidence sufficiency.

# 1. Introduction and Objectives

ProcureCheck checks a tender submission against a procurement checklist. It reports which required documents are present, missing or in need of human review. It never scores, ranks or recommends an award.

Week 2 produced a working baseline that read a whole submission in one model call. That approach limited submissions to about 45 pages. It also gave the model no reference material beyond the checklist.

Week 3 introduced retrieval-augmented generation. The aim was to answer from cited passages of a known document set rather than from the model's memory.

The objectives for Week 3 were:

1. To assemble a controlled corpus of 10 to 50 documents and record the provenance of each.
2. To implement ingestion, chunking, indexing and retrieval over that corpus.
3. To construct model context from retrieved evidence and show sources in the response or trace.
4. To create at least 15 RAG test questions covering answerable, partially answerable and unanswerable cases.
5. To document at least three retrieval or grounding failures and their causes.

# 2. Background

Retrieval-augmented generation pairs a language model with a search step (Lewis et al., 2020). The model answers from retrieved passages instead of from its parameters alone. Each answer can then cite its source.

Two families of search are in common use. Keyword search ranks passages by shared terms, usually with the BM25 formula (Robertson and Zaragoza, 2009). Dense search ranks passages by the similarity of learned embedding vectors. Keyword search misses paraphrases, while dense search can miss exact names and numbers.

Reciprocal rank fusion merges several rankings into one (Cormack et al., 2009). Each passage scores by its rank in each list, so neither method dominates.

Retrieval brings its own risks. A passage can be split from its heading, or a table can lose its structure in extraction. Similar legal wording can also make an unrelated passage look relevant. Barnett et al. (2024) listed missing content and missed top-ranked documents among common failure points.

# 3. Methodology and Procedure

## 3.1 Corpus Assembly

The corpus held 35 documents (Bataringaya, 2026). Thirty were official publications of the Public Procurement and Disposal of Public Assets Authority. These included standard bidding documents, user guides, regulations and guidelines. Five were synthetic tender submissions written for testing. Each synthetic submission tested one condition: complete, missing items, alternative wording, ambiguous clauses or distractors.

Provenance was recorded in a corpus manifest giving each document's identifier, title and file name. Eight files could not be read directly. Five legacy Word files were converted to the current Word format. Three scanned PDFs had no text layer and were passed through optical character recognition. A derivations log recorded the method, tool and date for each derived file. OCR text was marked as unverified.

## 3.2 Ingestion, Chunking and Indexing

Each document was segmented in reading order into blocks. A block was a paragraph, a table row or a PDF text block. Each block carried its page number and the heading it sat under.

Blocks were packed into passages of about 220 words, with a limit of 320. Table 1 lists the chunking rules and the failure each rule addressed.

<!-- Table: Chunking rules and the failures they addressed -->
| Rule | Failure addressed |
| --- | --- |
| A passage never crosses a heading | A clause title separated from its operative text |
| Document title and heading path indexed with each passage | A passage opening mid-clause lost its topic words |
| Each passage linked to its neighbours | One passage too short to hold a whole clause |
| Table rows kept in body order | A table cell bound to the wrong header |

The resulting 3,974 passages were indexed twice. A BM25 index served keyword search. The nomic-embed-text model produced 768-dimension vectors for dense search through the local Ollama server.

## 3.3 Search, Sources and Traces

Search ran both indexes and fused the rankings by reciprocal rank. Each result showed its document, page, heading path and rank in both lists. Every search wrote a trace file recording the query, each ranked passage and the scores.

An evidence-sufficiency test was added. Evidence was called sufficient when the best cosine similarity reached 0.65.

The context construction specification defined how retrieved passages would enter the model prompt (Mwesigwa, 2026). Each passage was wrapped in a tagged block carrying its chunk identifier, page, section and score. The model was to cite a chunk identifier for every positive finding. When no passage cleared the threshold, the prompt was to carry an explicit notice of no evidence.

## 3.4 Test Questions and Procedure

Retrieval quality was measured first. Twenty labelled queries were written from the corpus before any search ran. Fifteen had a known answering passage and five had no answer in the corpus. Each query was run in keyword, dense and hybrid modes.

The team's 16 RAG test questions were then run (Johnson, 2026). Six were answerable, five partially answerable and five deliberately unanswerable. Each question passed first through the safety guard. Allowed questions were then searched in hybrid mode, taking the top five passages.

Hit at k was the share of answerable queries whose answering passage ranked in the top k. Mean reciprocal rank averaged one over that rank. Cosine similarity was a unitless score from 0 to 1.

## 3.5 Problems Encountered

Three problems arose.

PDF title lines that wrapped were read as separate headings. Passages were cut into one-line fragments. A stricter heading rule for PDF and OCR text was introduced.

Running page headers were repeated in every passage and distorted the keyword index. They were detected and removed.

Embedding the full corpus took most of the build time. A rebuild was changed to reuse embeddings for unchanged text.

# 4. Results

Hybrid search performed best of the three modes. Table 2 compares them on the 15 answerable queries.

<!-- Table: Retrieval quality by search mode on 15 answerable queries -->
| Mode | Hit at 1 | Hit at 5 | Hit at 10 | Mean reciprocal rank |
| --- | --- | --- | --- | --- |
| Keyword (BM25) | 60% | 73% | 87% | 0.66 |
| Meaning (embeddings) | 53% | 73% | 80% | 0.62 |
| Hybrid (fusion) | 60% | 80% | 93% | 0.68 |

Keyword search alone missed two queries that dense search found at rank one or two. Dense search missed three queries that keyword search found. Hybrid search missed only one query. That query concerned bid security, and its answer sat in scanned text from DOC-025.

Answerable queries reached a best similarity between 0.732 and 0.860. The five out-of-corpus queries reached between 0.515 and 0.761. One out-of-corpus query was therefore called sufficient.

Table 3 summarises the run of the team's 16 RAG test questions.

<!-- Table: Team RAG test questions by expected behaviour -->
| Question type | Questions | Refused by guard | Called sufficient | Top passage from a bidder submission |
| --- | --- | --- | --- | --- |
| Answerable | Q1 to Q6 | 0 of 6 | 6 of 6 | 1 of 6 |
| Partially answerable | Q7 to Q11 | 0 of 5 | 5 of 5 | 1 of 5 |
| Deliberately unanswerable | Q12 to Q16 | 2 of 5 | 3 of 3 allowed | 0 of 3 allowed |

The guard refused Q14 as a ranking request and Q15 as an award recommendation. Neither reached search. Q13 asked for a bid's total value and Q16 asked for a general legal judgement. Both passed the guard.

Every allowed question cleared the 0.65 threshold. Best similarity ranged from 0.655 to 0.834. The three allowed unanswerable questions scored 0.713, 0.772 and 0.780. The lowest of these, 0.713, was higher than three answerable questions.

Most top passages came from regulatory guidance, not from a bidder's submission. For example, Q3 asked whether "the submission" held a bid securing declaration. Its top passage was the clause in a standard bidding document requiring one.

The failure analysis documented four failure classes (Mwesigwa and Bataringaya, 2026). These were chunk boundary splits, shared legal boilerplate, flattened tables and a certificate held by a subcontractor. Its scenarios were illustrative and were not drawn from runs of this system.

# 5. Discussion

The questions exposed a scope mismatch. They asked about one bidder's package, but search ran over the whole corpus. Regulatory text about a document looks very similar to the document itself. Search therefore returned the rule requiring a bid securing declaration when asked for the declaration.

The questions also referred to a submission, MUK/SUPP/2026/0012, that was not in the corpus. The expected answers could not be confirmed against any indexed text. The run therefore measured routing and sufficiency, not answer accuracy.

The sufficiency threshold did not separate answerable from unanswerable questions. Procurement documents share much vocabulary, so almost any procurement question finds a close passage. Barnett et al. (2024) described the same risk when the answer is missing from the corpus. Similarity measures closeness of topic, not whether a passage answers the question.

The Week 2 finding recurred in a new form. A search always offers a nearest match. In Week 2 the fix was a second model call that judged the quoted passage with the document withheld. The same judging step is likely needed for retrieved evidence.

The guard handled the clearest boundary cases in code, with no model call. Q13 and Q16 showed its limits. A question about bid value or general legal compliance used none of the guarded phrases. Such questions reached search and returned confident-looking passages.

Several remedies in the failure analysis were not built. Cross-encoder reranking, layout-aware table parsing and entity checks remained proposals. Retrieval was also not yet connected to the completeness check itself. The check still read each submission whole.

# 6. Conclusion

A controlled corpus was assembled, indexed and made searchable with sources and traces in Week 3. Sixteen test questions and four failure classes were documented. Objectives 1, 2, 4 and 5 were met. Objective 3 was met for search results and traces, and specified for model context.

The main lesson was that finding a relevant passage differs from finding an answer. Hybrid search ranked answering passages well. It could not tell when the corpus held no answer.

Retrieval was not yet ready to replace reading the whole submission. Its results still needed a scope limit and a judging step before a procurement officer could rely on them.

# 7. Recommendations

- Search should be limited to the submission under check when a question concerns a bidder's documents.
- Regulatory guidance should be searched separately, to explain what a requirement means.
- Each retrieved passage should be judged by a second model call before it is cited as evidence.
- The Week 3 test questions should be rewritten against a submission that is in the corpus, with page-level answer keys.
- The safety guard should be extended to questions about bid prices and general legal compliance.
- Retrieval should be connected to the completeness check, with the context format from the specification.

# References

Barnett, S., Kurniawan, S., Thudumu, S., Brannelly, Z., and Abdelrazek, M. (2024). *Seven failure points when engineering a retrieval augmented generation system* (arXiv:2401.05856). arXiv. https://arxiv.org/abs/2401.05856

Bataringaya, B. (2026). *Controlled corpus, Group H* [Unpublished project dataset]. Group H (Evening), BSE4104, Makerere University.

Cormack, G. V., Clarke, C. L. A., and Buettcher, S. (2009). Reciprocal rank fusion outperforms Condorcet and individual rank learning methods. In *Proceedings of the 32nd International ACM SIGIR Conference on Research and Development in Information Retrieval* (pp. 758-759). ACM. https://doi.org/10.1145/1571941.1572114

Johnson, M. (2026). *ProcureCheck Week 3 RAG test questions* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Lewis, P., et al. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. In *Advances in Neural Information Processing Systems 33* (pp. 9459-9474). https://arxiv.org/abs/2005.11401

Mwesigwa, I. (2026). *Context construction and source attribution traceability specification* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Mwesigwa, I., and Bataringaya, B. (2026). *Retrieval and grounding failure analysis* [Unpublished project document]. Group H (Evening), BSE4104, Makerere University.

Robertson, S., and Zaragoza, H. (2009). The probabilistic relevance framework: BM25 and beyond. *Foundations and Trends in Information Retrieval, 3*(4), 333-389. https://doi.org/10.1561/1500000019
