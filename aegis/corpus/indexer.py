"""
Corpus Indexer -- builds and persists FAISS + MinHash indices for large corpora.

Supports incremental addition, serialization to disk, and loading from disk
so the index does not need to be rebuilt on every run.

Index storage layout (--index-dir):
    corpus_meta.json      -- list of {label, source_path, added_at, word_count}
    corpus_texts.json     -- list of [label, full_text] -- the actual corpus
                             content, reloaded on restart so build_indices()
                             and rebuilds work without re-parsing source files
    ngram_word_index.json -- {key: [label, paragraph_text]} for the word index
    ngram_char_index.json -- {key: [label, paragraph_text]} for the char index
    ngram_config.json     -- {num_perm, word_threshold, char_threshold} used
                             to rebuild matching MinHashLSH objects on load
    semantic.faiss        -- FAISS flat index (native binary format)
    semantic_texts.json   -- [[label, sentence], ...] parallel list

No pickle is used anywhere in this module. The MinHash/MinHashLSH objects are
never serialized directly -- on load, each stored paragraph's MinHash is
recomputed from its plain text and re-inserted into a fresh MinHashLSH. This
is deterministic (same text -> same MinHash) and avoids the arbitrary-code-
execution risk of unpickling data that could, in principle, have been placed
in the index directory by another process (e.g. via the REST API's
/corpus/add and /corpus/build endpoints).

All writes are atomic: each file is written to a temporary path in the same
directory and then moved into place with os.replace(), so a crash or
concurrent read during a rebuild can never observe a partially-written file.
"""

from __future__ import annotations
import os
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from aegis.core.document import DocumentParser

logger = logging.getLogger(__name__)


def _atomic_write_text(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _atomic_write_json(path: Path, obj) -> None:
    _atomic_write_text(path, json.dumps(obj, indent=2, ensure_ascii=False))


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
        self._corpus: list[tuple[str, str]] = []  # (label, text)

        meta_path = self.index_dir / "corpus_meta.json"
        if meta_path.exists():
            with open(meta_path, encoding="utf-8") as f:
                self._meta = json.load(f)
            logger.info("Loaded corpus meta: %d entries", len(self._meta))

        texts_path = self.index_dir / "corpus_texts.json"
        if texts_path.exists():
            with open(texts_path, encoding="utf-8") as f:
                self._corpus = [tuple(pair) for pair in json.load(f)]
            logger.info("Loaded corpus text for %d document(s)", len(self._corpus))
        elif self._meta:
            logger.warning(
                "corpus_meta.json exists but corpus_texts.json is missing -- "
                "%d document(s) are known by label but their text was not "
                "persisted (index built with an older AEGIS version). "
                "Re-add these documents to make them rebuildable.",
                len(self._meta),
            )

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
        self._save_corpus_texts()
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
        (Re)build all indices from the complete stored corpus (including
        documents added in a previous process, reloaded from corpus_texts.json).
        Writes index files to index_dir atomically.
        """
        if not self._corpus:
            logger.warning(
                "No documents in corpus; load with add_document() first, "
                "or check that corpus_texts.json was persisted on a prior run")
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

        _atomic_write_json(
            self.index_dir / "ngram_config.json",
            {
                "num_perm": num_perm,
                "word_threshold": word_threshold,
                "char_threshold": char_threshold,
            },
        )
        _atomic_write_json(
            self.index_dir / "ngram_word_index.json",
            {k: list(v) for k, v in det._word_index.items()},
        )
        _atomic_write_json(
            self.index_dir / "ngram_char_index.json",
            {k: list(v) for k, v in det._char_index.items()},
        )
        logger.info("N-gram index saved (%d word keys, %d char keys)",
                    len(det._word_index), len(det._char_index))

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

        faiss_path = self.index_dir / "semantic.faiss"
        tmp_faiss_path = faiss_path.with_suffix(".faiss.tmp")
        faiss.write_index(index, str(tmp_faiss_path))
        os.replace(tmp_faiss_path, faiss_path)

        _atomic_write_json(
            self.index_dir / "semantic_texts.json",
            [list(pair) for pair in texts_meta],
        )
        logger.info("Semantic index saved: %d sentence embeddings", len(texts_meta))

    def load_ngram_detector(self):
        """
        Return a fully-populated NGramDetector reconstructed from persisted
        index files. Each stored paragraph's MinHash is recomputed from its
        plain text and re-inserted into fresh MinHashLSH objects -- no
        MinHash/LSH object is ever deserialized, only plain JSON text.
        """
        from aegis.detectors.ngram import NGramDetector
        from datasketch import MinHashLSH

        config_path = self.index_dir / "ngram_config.json"
        word_index_path = self.index_dir / "ngram_word_index.json"
        char_index_path = self.index_dir / "ngram_char_index.json"
        for path in (config_path, word_index_path, char_index_path):
            if not path.exists():
                raise FileNotFoundError(
                    f"Index file missing: {path}. Run build_indices() first.")

        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
        with open(word_index_path, encoding="utf-8") as f:
            word_index = {k: tuple(v) for k, v in json.load(f).items()}
        with open(char_index_path, encoding="utf-8") as f:
            char_index = {k: tuple(v) for k, v in json.load(f).items()}

        det = NGramDetector(
            num_perm=config["num_perm"],
            word_threshold=config["word_threshold"],
            char_threshold=config["char_threshold"],
        )
        det._word_lsh = MinHashLSH(threshold=det.word_threshold, num_perm=det.num_perm)
        det._char_lsh = MinHashLSH(threshold=det.char_threshold, num_perm=det.num_perm)
        det._word_index = word_index
        det._char_index = char_index

        for key, (_label, text) in word_index.items():
            try:
                det._word_lsh.insert(key, det._word_minhash(text))
            except ValueError:
                pass
        for key, (_label, text) in char_index.items():
            try:
                det._char_lsh.insert(key, det._char_minhash(text))
            except ValueError:
                pass

        return det

    def load_semantic_detector(self):
        """Return a pre-loaded SemanticDetector from persisted FAISS index."""
        import faiss
        from aegis.detectors.semantic import SemanticDetector

        faiss_path = self.index_dir / "semantic.faiss"
        texts_path = self.index_dir / "semantic_texts.json"
        if not faiss_path.exists() or not texts_path.exists():
            raise FileNotFoundError(
                "Semantic index missing. Run build_indices() first.")

        det = SemanticDetector(device=self.device)
        det._load_models()
        det._index = faiss.read_index(str(faiss_path))
        with open(texts_path, encoding="utf-8") as f:
            det._index_texts = [tuple(pair) for pair in json.load(f)]
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
        _atomic_write_json(self.index_dir / "corpus_meta.json", self._meta)

    def _save_corpus_texts(self) -> None:
        _atomic_write_json(
            self.index_dir / "corpus_texts.json",
            [list(pair) for pair in self._corpus],
        )
