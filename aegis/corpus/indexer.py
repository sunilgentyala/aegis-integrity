"""
Corpus Indexer -- builds and persists FAISS + MinHash indices for large corpora.

Supports incremental addition, serialization to disk, and loading from disk
so the index does not need to be rebuilt on every run.

Index storage layout (--index-dir):
    corpus_meta.json      -- list of {label, source_path, added_at}
    ngram_word.pkl        -- MinHashLSH (pickle)
    ngram_char.pkl        -- MinHashLSH (pickle)
    ngram_word_index.pkl  -- {key: (label, text)}
    ngram_char_index.pkl  -- {key: (label, text)}
    semantic.faiss        -- FAISS flat index (binary)
    semantic_texts.pkl    -- [(label, sentence)] parallel list
"""

from __future__ import annotations
import os
import json
import pickle
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aegis.core.document import DocumentParser

logger = logging.getLogger(__name__)


class CorpusIndexer:
    """
    Build, persist, and query combined n-gram + semantic corpus indices.
    """

    def __init__(self, index_dir: str, device: str = "cpu"):
        self.index_dir = Path(index_dir)
        self.index_dir.mkdir(parents=True, exist_ok=True)
        self.device = device
        self._parser = DocumentParser()
        self._meta: list[dict] = []
        self._corpus: list[tuple[str, str]] = []  # (label, text) for in-memory use

        meta_path = self.index_dir / "corpus_meta.json"
        if meta_path.exists():
            with open(meta_path) as f:
                self._meta = json.load(f)
            logger.info("Loaded corpus meta: %d entries", len(self._meta))

    def add_document(self, path: str, label: Optional[str] = None) -> str:
        """
        Parse a document and add it to the corpus index.
        Returns the label assigned to the document.
        """
        doc = self._parser.parse(path)
        label = label or Path(path).stem
        text = doc.full_text

        self._meta.append({
            "label": label,
            "source_path": path,
            "added_at": datetime.now(timezone.utc).isoformat(),
            "word_count": len(text.split()),
        })
        self._corpus.append((label, text))
        self._save_meta()
        logger.info("Added '%s' (%d words)", label, len(text.split()))
        return label

    def add_directory(self, directory: str, pattern: str = "*.pdf") -> list[str]:
        """
        Recursively add all matching files from a directory.
        """
        labels = []
        for path in Path(directory).rglob(pattern):
            try:
                label = self.add_document(str(path))
                labels.append(label)
            except Exception as exc:
                logger.warning("Failed to index %s: %s", path, exc)
        return labels

    def build_indices(
        self,
        num_perm: int = 128,
        word_threshold: float = 0.25,
        char_threshold: float = 0.40,
    ) -> None:
        """
        (Re)build all indices from the current corpus.
        Writes index files to index_dir.
        """
        if not self._corpus:
            logger.warning("No documents in corpus; load with add_document() first")
            return

        self._build_ngram_index(num_perm, word_threshold, char_threshold)
        self._build_semantic_index()
        logger.info("All indices built and saved to %s", self.index_dir)

    def _build_ngram_index(
        self, num_perm: int, word_threshold: float, char_threshold: float
    ) -> None:
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector(
            num_perm=num_perm,
            word_threshold=word_threshold,
            char_threshold=char_threshold,
        )
        det.build_index(self._corpus)

        with open(self.index_dir / "ngram_word.pkl", "wb") as f:
            pickle.dump(det._word_lsh, f)
        with open(self.index_dir / "ngram_char.pkl", "wb") as f:
            pickle.dump(det._char_lsh, f)
        with open(self.index_dir / "ngram_word_index.pkl", "wb") as f:
            pickle.dump(det._word_index, f)
        with open(self.index_dir / "ngram_char_index.pkl", "wb") as f:
            pickle.dump(det._char_index, f)
        logger.info("N-gram index saved")

    def _build_semantic_index(self) -> None:
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
        except ImportError:
            logger.warning(
                "FAISS/sentence-transformers not installed; semantic index skipped")
            return

        import re
        model = SentenceTransformer(
            "paraphrase-MiniLM-L6-v2", device=self.device)

        texts_meta: list[tuple[str, str]] = []
        for label, text in self._corpus:
            for sent in re.split(r"(?<=[.!?])\s+(?=[A-Z])", text):
                sent = sent.strip()
                if len(sent.split()) >= 8:
                    texts_meta.append((label, sent))

        if not texts_meta:
            return

        sents = [t for _, t in texts_meta]
        vecs = model.encode(sents, batch_size=64,
                            normalize_embeddings=True,
                            show_progress_bar=True)
        dim = vecs.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vecs.astype("float32"))

        faiss.write_index(index, str(self.index_dir / "semantic.faiss"))
        with open(self.index_dir / "semantic_texts.pkl", "wb") as f:
            pickle.dump(texts_meta, f)
        logger.info("Semantic index saved: %d sentence embeddings", len(texts_meta))

    def load_ngram_detector(self):
        """Return a pre-loaded NGramDetector from persisted index files."""
        from aegis.detectors.ngram import NGramDetector
        det = NGramDetector()
        for fname, attr in [
            ("ngram_word.pkl", "_word_lsh"),
            ("ngram_char.pkl", "_char_lsh"),
            ("ngram_word_index.pkl", "_word_index"),
            ("ngram_char_index.pkl", "_char_index"),
        ]:
            path = self.index_dir / fname
            if not path.exists():
                raise FileNotFoundError(
                    f"Index file missing: {path}. Run build_indices() first.")
            with open(path, "rb") as f:
                setattr(det, attr, pickle.load(f))
        return det

    def load_semantic_detector(self):
        """Return a pre-loaded SemanticDetector from persisted FAISS index."""
        import faiss
        import pickle
        from aegis.detectors.semantic import SemanticDetector

        faiss_path = self.index_dir / "semantic.faiss"
        texts_path = self.index_dir / "semantic_texts.pkl"
        if not faiss_path.exists() or not texts_path.exists():
            raise FileNotFoundError(
                "Semantic index missing. Run build_indices() first.")

        det = SemanticDetector(device=self.device)
        det._load_models()
        det._index = faiss.read_index(str(faiss_path))
        with open(texts_path, "rb") as f:
            det._index_texts = pickle.load(f)
        return det

    def corpus_summary(self) -> dict:
        return {
            "document_count": len(self._meta),
            "index_dir": str(self.index_dir),
            "documents": [
                {"label": m["label"], "word_count": m.get("word_count", "?"),
                 "added_at": m["added_at"]}
                for m in self._meta
            ],
        }

    def _save_meta(self) -> None:
        with open(self.index_dir / "corpus_meta.json", "w") as f:
            json.dump(self._meta, f, indent=2)
