# Week 3 RAG Test Question Run

Run 2026-09-23T17:52. Index built 2026-09-17T00:11:52+00:00, 3974 chunks, embeddings from nomic-embed-text. Hybrid search, top 5, sufficiency threshold 0.65.

The questions target a submission (MUK/SUPP/2026/0012) that is not in the corpus. "Submission hits" counts how many of the top 5 passages came from a synthetic bidder submission (DOC-031 to DOC-035) rather than from regulatory guidance.

| ID | Kind | Guard | Best cosine | Sufficient | Submission hits (top 5) | Top passage |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | answerable | allowed | 0.766 | yes | 1 | DOC-002, p. 22, Submission of Bid |
| Q2 | answerable | allowed | 0.721 | yes | 1 | DOC-014, Section 4: Bidding Forms > Form 4 Bidder Information Sheet |
| Q3 | answerable | allowed | 0.834 | yes | 0 | DOC-014, Section 1: Instructions to Bidders > Bid Security or Bid Securing Declaration |
| Q4 | answerable | allowed | 0.708 | yes | 0 | DOC-009, p. 12, General > Documents Establishing the Eligibility of Supplies |
| Q5 | answerable | allowed | 0.687 | yes | 0 | DOC-001, p. 11, General > Bid Security or Bid Securing Declaration |
| Q6 | answerable | allowed | 0.687 | yes | 1 | DOC-033, Revenue Compliance Evidence |
| Q7 | partially answerable | allowed | 0.751 | yes | 4 | DOC-031, 3. Tax Clearance Certificate |
| Q8 | partially answerable | allowed | 0.776 | yes | 0 | DOC-012, p. 11, Guidance Notes on Section 2: Bidding Forms > Bid-Securing Declaration |
| Q9 | partially answerable | allowed | 0.752 | yes | 0 | DOC-014, Section 1: Instructions to Bidders > Format and Signing of Bid |
| Q10 | partially answerable | allowed | 0.655 | yes | 0 | DOC-014, Section 4: Bidding Forms > Form 5A Pending Litigation |
| Q11 | partially answerable | allowed | 0.738 | yes | 1 | DOC-006, p. 16, Section 1: Instructions to Consultants > Preliminary Examination of Proposals – Eligibility and Administrative Compliance |
| Q12 | unanswerable | allowed | 0.772 | yes | 0 | DOC-002, p. 22, Submission of Bid |
| Q13 | unanswerable | allowed | 0.713 | yes | 0 | DOC-022, p. 64, Part 1 - Section 3: Evaluation Methodology and Criteria > Lots |
| Q14 | unanswerable | refused (ranking) | - | - | - | - |
| Q15 | unanswerable | refused (award_recommendation) | - | - | - | - |
| Q16 | unanswerable | allowed | 0.78 | yes | 0 | DOC-029, p. 8, NOTICE OF BEST EVALUATED BIDDER |
