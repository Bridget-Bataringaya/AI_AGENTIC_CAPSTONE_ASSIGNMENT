"""The controlled corpus: which documents exist and where their text comes from.

The corpus was assembled by the team in Week 3 (CORPUS_GROUP_H, ClickUp task
123tcvwe2y4). CORPUS_MANIFEST.csv names every document and
Public_Procurement_Corpus_Provenance_Register.pdf records where each came from.
Neither is edited here.

Eight documents cannot be read as filed. Five are legacy Word 97-2003 files and
three are scanned PDFs with no text layer. Their readable text lives under
derived/, and DERIVATIONS.csv records how each derived file was produced. A
chunk taken from derived text carries that fact with it (`extraction`), so a
reviewer is told when a quotation came from OCR rather than from the document.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Final, List, Optional

from ..checklists import REPO_ROOT

CORPUS_DIR: Final[Path] = REPO_ROOT / "knowledge" / "corpus"
MANIFEST_NAME: Final[str] = "CORPUS_MANIFEST.csv"
DERIVATIONS_NAME: Final[str] = "DERIVATIONS.csv"
DOCUMENTS_SUBDIR: Final[str] = "documents"

EXTRACTION_NATIVE: Final[str] = "native"
EXTRACTION_CONVERTED: Final[str] = "converted"
EXTRACTION_OCR: Final[str] = "ocr"

KIND_OFFICIAL: Final[str] = "official"
KIND_SYNTHETIC: Final[str] = "synthetic"


class CorpusError(ValueError):
    """Raised when the manifest and the files on disk disagree."""


@dataclass(frozen=True)
class CorpusDocument:
    """One manifest entry, resolved to the file its text will be read from."""

    doc_id: str
    title: str
    original_path: Path
    text_source: Path
    extraction: str

    @property
    def kind(self) -> str:
        """Official PPDA source or team-made synthetic submission.

        The register states DOC-031 to DOC-035 are synthetic; their titles say
        so too, which is what is checked, so a renumbered corpus stays correct.
        """
        return KIND_SYNTHETIC if "synthetic" in self.title.lower() else KIND_OFFICIAL


def _read_derivations(corpus_dir: Path) -> Dict[str, Dict[str, str]]:
    path = corpus_dir / DERIVATIONS_NAME
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8", newline="") as handle:
        return {row["Document ID"].strip(): row for row in csv.DictReader(handle)}


def _extraction_for(method: str) -> str:
    return EXTRACTION_OCR if method.lower().startswith("ocr") else EXTRACTION_CONVERTED


def load_corpus(
    corpus_dir: Path = CORPUS_DIR, doc_ids: Optional[List[str]] = None
) -> List[CorpusDocument]:
    """Read the manifest and resolve each document to a readable text source.

    Fails loudly when a listed file is missing, because an index silently built
    over part of the corpus would answer "not found" for documents that exist.
    """
    manifest = corpus_dir / MANIFEST_NAME
    if not manifest.is_file():
        raise CorpusError(f"No corpus manifest at {manifest}.")

    derivations = _read_derivations(corpus_dir)
    wanted = {doc_id.upper() for doc_id in doc_ids} if doc_ids else None
    documents: List[CorpusDocument] = []

    with manifest.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            doc_id = row["Document ID"].strip()
            if wanted is not None and doc_id.upper() not in wanted:
                continue
            original = corpus_dir / DOCUMENTS_SUBDIR / row["File Name"].strip()
            if not original.is_file():
                raise CorpusError(f"{doc_id} is in the manifest but {original} is missing.")

            derived = derivations.get(doc_id)
            if derived:
                source = corpus_dir / derived["Derived text source"].strip()
                if not source.exists():
                    raise CorpusError(f"{doc_id} derived text {source} is missing.")
                extraction = _extraction_for(derived["Method"])
            else:
                source, extraction = original, EXTRACTION_NATIVE

            documents.append(
                CorpusDocument(
                    doc_id=doc_id,
                    title=row["Document Title"].strip(),
                    original_path=original,
                    text_source=source,
                    extraction=extraction,
                )
            )

    if wanted is not None:
        missing = wanted - {document.doc_id.upper() for document in documents}
        if missing:
            raise CorpusError(f"Not in the manifest: {', '.join(sorted(missing))}.")
    return documents
