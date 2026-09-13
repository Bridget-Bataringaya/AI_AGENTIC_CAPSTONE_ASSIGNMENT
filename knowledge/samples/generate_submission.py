"""Generate the synthetic tender submission used for baseline testing.

The submission is synthetic. It contains no real bidder, no real procuring
entity, and no confidential information, in line with the Project Charter's
data-access constraint.

Seven of the ten checklist items are present, deliberately worded differently
from the checklist so that the run tests semantic matching rather than keyword
matching. Three are omitted on purpose:

    CHK-05  Anti-bribery and anti-corruption declaration
    CHK-07  Beneficial ownership disclosure form
    CHK-10  Certificate of non-blacklisting or non-debarment

Run:  python knowledge/samples/generate_submission.py
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

OUTPUT = Path(__file__).with_name("synthetic-submission.pdf")

PAGES: List[Tuple[str, str]] = [
    (
        "SECTION 1 - BID SUBMISSION COVER",
        "Tender Reference: SYN/WORKS/2026/014\n"
        "Procuring Entity: Synthetic District Local Government (illustrative only)\n"
        "Bidder: Kavuma Civil Works Limited (fictional entity)\n"
        "Bid Submission Date: 12 March 2026\n\n"
        "This bid is submitted in response to the invitation to bid for the\n"
        "construction of a district water access facility. All documents listed\n"
        "in the table of contents are enclosed in this package.",
    ),
    (
        "SECTION 2 - COMPANY REGISTRATION",
        "Attached as Appendix A is the Certificate of Registration of the Company\n"
        "issued by the Registrar of Companies, registration number SYN-114-2019,\n"
        "dated 08 August 2019, confirming that Kavuma Civil Works Limited is duly\n"
        "incorporated and remains in good standing.\n\n"
        "A certified copy of the company trading licence for the current year is\n"
        "attached immediately after the registration certificate.",
    ),
    (
        "SECTION 3 - REVENUE AUTHORITY COMPLIANCE",
        "The bidder encloses a Tax Clearance Certificate issued by the national\n"
        "revenue authority, reference TCC/2026/00417, valid from 01 January 2026\n"
        "to 31 December 2026. The certificate confirms that the bidder has no\n"
        "outstanding tax obligations as at the date of issue.",
    ),
    (
        "SECTION 4 - FINANCIAL POSITION",
        "Appendix C contains the audited accounts of the bidder for the financial\n"
        "years ended 30 June 2024 and 30 June 2025, prepared and signed by an\n"
        "independent firm of certified public accountants. Both sets of accounts\n"
        "carry an unqualified audit opinion.\n\n"
        "A bank reference letter confirming the bidder's credit standing is also\n"
        "enclosed for information.",
    ),
    (
        "SECTION 5 - BID GUARANTEE",
        "A bid guarantee in the sum of UGX 24,000,000.00 has been issued in favour\n"
        "of the Procuring Entity by Synthetic Commercial Bank Limited, guarantee\n"
        "number BG/2026/0221, valid for one hundred and twenty (120) days from the\n"
        "bid submission deadline, in the form prescribed in the bidding document.",
    ),
    (
        "SECTION 6 - RECORD OF SIMILAR ASSIGNMENTS",
        "The bidder has completed the following comparable contracts:\n\n"
        "  1. Construction of a gravity flow water scheme, 2023, UGX 410,000,000.00\n"
        "  2. Rehabilitation of four community boreholes, 2024, UGX 168,500,000.00\n"
        "  3. Construction of a district storage reservoir, 2025, UGX 522,000,000.00\n\n"
        "Completion certificates for each assignment are attached at Appendix E.",
    ),
    (
        "SECTION 7 - DECLARATIONS AND AUTHORISATION",
        "Declaration of Interest: The bidder confirms that no director, officer or\n"
        "shareholder of Kavuma Civil Works Limited holds any interest, direct or\n"
        "indirect, in the Procuring Entity, and that no circumstance exists that\n"
        "would place the bidder in a position of conflict in respect of this\n"
        "procurement. Signed by the Managing Director, 12 March 2026.\n\n"
        "Authority of Signatory: A notarised instrument of authority is enclosed,\n"
        "executed under the common seal of the company on 02 March 2026,\n"
        "appointing Mr. S. Kavuma, Managing Director, as the person authorised to\n"
        "sign, submit and negotiate this bid on behalf of the company.",
    ),
]


def build() -> Path:
    import fitz  # PyMuPDF

    document = fitz.open()
    for heading, body in PAGES:
        page = document.new_page()
        page.insert_text((60, 70), heading, fontname="helv", fontsize=13)
        page.insert_text((60, 105), body, fontname="helv", fontsize=10)
    document.save(OUTPUT)
    document.close()
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({len(PAGES)} pages)")
