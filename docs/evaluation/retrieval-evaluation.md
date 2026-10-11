# Retrieval Evaluation

Keyword, meaning and hybrid search over the controlled corpus

## 1. Scope

The evaluation ran over the index built 2026-09-17T00:11:52+00:00: 35 documents, 3974 chunks, and embeddings from nomic-embed-text. It used 15 answerable queries and 5 out-of-corpus queries from tests/evaluation/retrieval_cases.py. The answer key for each query was written from the corpus before any search was run. The run is reproduced with python run.py evaluate-retrieval.

## 2. Ranking quality

Table 1 gives, for each search mode, the share of answerable queries whose answering passage ranked first, in the top 5 and in the top 10, and the mean reciprocal rank.

Table 1: Ranking quality by search mode

| Mode | Hit at 1 | Hit at 5 | Hit at 10 | Mean reciprocal rank |
| --- | --- | --- | --- | --- |
| Keyword (BM25) | 60% | 73% | 87% | 0.66 |
| Meaning (embeddings) | 53% | 73% | 80% | 0.62 |
| Hybrid (RRF) | 60% | 80% | 93% | 0.68 |

## 3. Rank of the answering passage per query

Table 2 lists every answerable query with the rank at which each mode first returned a passage from the answer key, and the passage hybrid search ranked first.

Table 2: First relevant rank per query

| Case | Query | Keyword | Meaning | Hybrid | Hybrid top result |
| --- | --- | --- | --- | --- | --- |
| RC-01 | What form of bid security is required for open domestic bidding for supplies and works? | 5 | not in top 10 | not in top 10 | DOC-025, p. 3, PROCUREMENT ANO OISPOSAL |
| RC-02 | Which steps can be skipped when an entity uses micro procurement? | 1 | 1 | 1 | DOC-030, p. 17, Part III—Methods of Procurement > 22. Rules for micro procurement. |
| RC-03 | How does the guideline define aggregated requirements? | 8 | 8 | 6 | DOC-027, p. 2, GENERAL PROVISIONS ON PROCUREMENT OF AGGREGATED |
| RC-04 | What does a bidder use to log in to the electronic government procurement system? | 3 | not in top 10 | 2 | DOC-026, p. 13, PART IV - BIDDING AND EVALUATION |
| RC-05 | Which procurements are set aside for registered groups of women, youth and persons with disabilities? | 1 | 1 | 1 | DOC-017, p. 17, STANDARD BIDDING DOCUMENT FOR THE PROCUREMENTS RESERVED FOR REGISTERED ASSOCIATIONS OF WOMEN, YOUTH AND PERSONS WITH DISABILITIES > [Brief Description of the Procurement] - [Procurement Reference number] |
| RC-06 | Which documents prove a bidder is eligible, such as a tax clearance certificate and trading licence? | 1 | 2 | 1 | DOC-009, p. 29, Section 3: Evaluation Methodology and Criteria > Eligibility Criteria |
| RC-07 | For how long can a provider be suspended after failing a performance securing declaration? | 1 | 5 | 1 | DOC-001, p. 73, Performance Securing Declaration > To: |
| RC-08 | Which documents were deliberately left out of synthetic submission B? | 6 | 1 | 4 | DOC-032, Testing Note |
| RC-09 | Who signed the bid form for Nile Office Solutions? | 1 | 1 | 1 | DOC-031, 1. Signed Bid Form |
| RC-10 | How must a power of attorney signed outside Uganda be authenticated? | 1 | not in top 10 | 1 | DOC-014, Section 3: Evaluation Methodology and Criteria > Administrative Compliance Criteria |
| RC-11 | What planning records must a procuring and disposing entity keep on file? | not in top 10 | 1 | 8 | DOC-028, pp. 1-2, OF PUBLIC ASSETS AUTHORITY |
| RC-12 | What is the standard notice format announcing the best evaluated bidder for consultancy services? | 1 | 1 | 1 | DOC-029, pp. 5-6, CONSULTANCY SERVICES |
| RC-13 | Can the entity ask bidders to extend how long their bids remain valid? | 1 | 1 | 1 | DOC-001, p. 10, General > Bid Validity |
| RC-14 | When are bidders treated as having a conflict of interest, for example sharing controlling shareholders? | 1 | 1 | 1 | DOC-009, p. 5, General > Eligible Bidders |
| RC-15 | When does a bid securing declaration stop being valid? | not in top 10 | 2 | 5 | DOC-020, p. 11, General > Bid Security or Bid Securing Declaration |

## 4. Evidence sufficiency

Table 3 shows the best cosine similarity each query reached against any passage, and whether the configured threshold of 0.65 called the evidence sufficient.

Table 3: Best similarity and sufficiency call

| Case | Kind | Best cosine | Called sufficient |
| --- | --- | --- | --- |
| RC-01 | answerable | 0.795 | Yes |
| RC-02 | answerable | 0.769 | Yes |
| RC-03 | answerable | 0.806 | Yes |
| RC-04 | answerable | 0.778 | Yes |
| RC-05 | answerable | 0.860 | Yes |
| RC-06 | answerable | 0.815 | Yes |
| RC-07 | answerable | 0.749 | Yes |
| RC-08 | answerable | 0.796 | Yes |
| RC-09 | answerable | 0.804 | Yes |
| RC-10 | answerable | 0.732 | Yes |
| RC-11 | answerable | 0.795 | Yes |
| RC-12 | answerable | 0.853 | Yes |
| RC-13 | answerable | 0.801 | Yes |
| RC-14 | answerable | 0.751 | Yes |
| RC-15 | answerable | 0.815 | Yes |
| OC-01 | out-of-corpus | 0.622 | No |
| OC-02 | out-of-corpus | 0.515 | No |
| OC-03 | out-of-corpus | 0.563 | No |
| OC-04 | out-of-corpus | 0.549 | No |
| OC-05 | out-of-corpus | 0.761 | Yes |

Answerable queries reached between 0.732 and 0.860. Out-of-corpus queries reached between 0.515 and 0.761. The two ranges overlap, so no single threshold separates every case. Similarity alone cannot decide answerability, and the model must still be allowed to say that the evidence does not answer the question.
