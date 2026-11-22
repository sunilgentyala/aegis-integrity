"""
Regression tests for CorpusIndexer persistence.

Covers the reported bug: after a process restart, a rebuild would silently
operate on an empty in-memory corpus (only corpus_meta.json was reloaded,
not the actual document text), so previously-indexed documents vanished
from the rebuilt index.
"""

import json
from pathlib import Path


from aegis.corpus.indexer import CorpusIndexer


def _write_txt(tmp_path: Path, name: str, text: str) -> str:
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


DOC_A = (
    "Alpha document about isolation forest anomaly detection in enterprise "
    "DNS traffic monitoring systems and their operational deployment across "
    "distributed resolver infrastructure with continuous query log retention "
    "for downstream security analytics pipelines and threat hunting teams."
)
DOC_B = (
    "Bravo document about federated learning approaches for privacy "
    "preserving intrusion detection across distributed network segments "
    "operated by independent enterprise tenants sharing a common threat "
    "model without centralizing raw traffic captures on any single server."
)


class TestCorpusPersistence:

    def test_corpus_text_survives_restart(self, tmp_path):
        index_dir = str(tmp_path / "idx")

        indexer1 = CorpusIndexer(index_dir)
        indexer1.add_document(_write_txt(tmp_path, "a.txt", DOC_A), label="A")
        assert len(indexer1._corpus) == 1

        # Simulate a process restart: a brand new CorpusIndexer instance
        # pointed at the same directory, with no in-memory state carried over.
        indexer2 = CorpusIndexer(index_dir)
        assert len(indexer2._corpus) == 1, (
            "Document text was not reloaded from corpus_texts.json after restart"
        )
        assert indexer2._corpus[0][0] == "A"
        assert indexer2._corpus[0][1] == DOC_A

    def test_restart_add_and_rebuild_keeps_both_documents(self, tmp_path):
        """The exact regression scenario: add A, build, restart, add B,
        rebuild -- search must return matches from both A and B."""
        index_dir = str(tmp_path / "idx")

        indexer1 = CorpusIndexer(index_dir)
        indexer1.add_document(_write_txt(tmp_path, "a.txt", DOC_A), label="A")
        indexer1.build_indices()

        # Restart
        indexer2 = CorpusIndexer(index_dir)
        indexer2.add_document(_write_txt(tmp_path, "b.txt", DOC_B), label="B")
        indexer2.build_indices()

        assert len(indexer2._corpus) == 2
        labels = {label for label, _ in indexer2._corpus}
        assert labels == {"A", "B"}

        ngram_det = indexer2.load_ngram_detector()
        indexed_labels = {label for label, _ in ngram_det._word_index.values()}
        assert "A" in indexed_labels, "Document A was dropped from the rebuilt index"
        assert "B" in indexed_labels, "Document B is missing from the rebuilt index"

    def test_index_files_are_json_not_pickle(self, tmp_path):
        index_dir = tmp_path / "idx"
        indexer = CorpusIndexer(str(index_dir))
        indexer.add_document(_write_txt(tmp_path, "a.txt", DOC_A), label="A")
        indexer.build_indices()

        for name in ("corpus_meta.json", "corpus_texts.json",
                     "ngram_config.json", "ngram_word_index.json",
                     "ngram_char_index.json"):
            path = index_dir / name
            assert path.exists(), f"missing {name}"
            with open(path, encoding="utf-8") as f:
                json.load(f)  # must be valid JSON, not pickle

        assert not list(index_dir.glob("*.pkl")), "pickle files should not be written"

    def test_atomic_write_leaves_no_tmp_file_behind(self, tmp_path):
        index_dir = tmp_path / "idx"
        indexer = CorpusIndexer(str(index_dir))
        indexer.add_document(_write_txt(tmp_path, "a.txt", DOC_A), label="A")
        indexer.build_indices()

        assert not list(index_dir.glob("*.tmp")), "atomic write left a .tmp file behind"

    def test_corpus_summary_reflects_persisted_meta(self, tmp_path):
        index_dir = str(tmp_path / "idx")
        indexer1 = CorpusIndexer(index_dir)
        indexer1.add_document(_write_txt(tmp_path, "a.txt", DOC_A), label="A")

        indexer2 = CorpusIndexer(index_dir)
        summary = indexer2.corpus_summary()
        assert summary["document_count"] == 1
        assert summary["documents"][0]["label"] == "A"
