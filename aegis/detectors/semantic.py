"""
Semantic similarity detector using SBERT sentence embeddings + FAISS.

Uses paraphrase-MiniLM-L6-v2 (80 MB, offline after first download) for
dense retrieval, then a cross-encoder for precision re-ranking.

Fills gap: Existing open-source tools use BM25 or TF-IDF (lexical).
AEGIS adds dense semantic retrieval that catches concept-level paraphrase
where no exact words are shared -- a capability absent from all free tools.
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from typing import Optional


@dataclass
class SemanticMatch:
    query_sentence: str
    source_label: str
    source_sentence: str
    cosine_score: float
    rerank_score: Optional[float]   # cross-encoder score (None if not computed)
    is_paraphrase: bool


class SemanticDetector:
    """
    Dense semantic similarity using SBERT + optional FAISS index.
    Works on individual sentences or paragraphs.
    """

    EMBED_MODEL = "paraphrase-MiniLM-L6-v2"   # 80 MB, fast CPU inference
    RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(
        self,
        cosine_threshold: float = 0.82,
        rerank_threshold: float = 0.0,    # cross-encoder score (logit scale)
        use_reranker: bool = True,
        device: str = "cpu",
    ):
        self.cosine_threshold = cosine_threshold
        self.rerank_threshold = rerank_threshold
        self.use_reranker = use_reranker
        self.device = device
        self._model = None
        self._reranker = None
        self._index = None               # FAISS index
        self._index_texts: list[tuple[str, str]] = []  # (label, text)

    def _load_models(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer, CrossEncoder
            self._model = SentenceTransformer(self.EMBED_MODEL, device=self.device)
            if self.use_reranker:
                self._reranker = CrossEncoder(self.RERANK_MODEL, device=self.device)
        except ImportError:
            raise ImportError(
                "sentence-transformers required: pip install sentence-transformers")

    # ------------------------------------------------------------------
    # Index
    # ------------------------------------------------------------------

    def build_index(self, corpus: list[tuple[str, str]]) -> None:
        """
        corpus: list of (label, text) pairs.
        Embeds each sentence and stores in a FAISS flat index.
        """
        import faiss
        self._load_models()

        self._index_texts = []
        embeddings = []

        for label, text in corpus:
            sentences = self._split_sentences(text)
            for sent in sentences:
                if len(sent.split()) < 8:
                    continue
                self._index_texts.append((label, sent))

        if not self._index_texts:
            return

        texts = [t for _, t in self._index_texts]
        vecs = self._model.encode(texts, batch_size=64,
                                  show_progress_bar=False,
                                  normalize_embeddings=True)
        dim = vecs.shape[1]
        self._index = faiss.IndexFlatIP(dim)   # inner product on normalized = cosine
        self._index.add(vecs.astype("float32"))

    def find_matches(
        self, query_text: str, top_k: int = 5
    ) -> list[SemanticMatch]:
        """
        Find semantically similar sentences from the indexed corpus.
        """
        if self._index is None or self._index.ntotal == 0:
            return []
        self._load_models()

        query_sentences = [s for s in self._split_sentences(query_text)
                           if len(s.split()) >= 8]
        if not query_sentences:
            return []

        q_vecs = self._model.encode(query_sentences, batch_size=32,
                                    show_progress_bar=False,
                                    normalize_embeddings=True)
        scores, indices = self._index.search(
            q_vecs.astype("float32"), top_k)

        results: list[SemanticMatch] = []
        for qi, (score_row, idx_row) in enumerate(zip(scores, indices)):
            for score, idx in zip(score_row, idx_row):
                if idx < 0 or score < self.cosine_threshold:
                    continue
                label, src_sent = self._index_texts[idx]

                rerank_score = None
                if self._reranker:
                    rs = self._reranker.predict(
                        [(query_sentences[qi], src_sent)])
                    rerank_score = float(rs[0])

                is_para = (score >= self.cosine_threshold and
                           (rerank_score is None or
                            rerank_score >= self.rerank_threshold))

                results.append(SemanticMatch(
                    query_sentence=query_sentences[qi],
                    source_label=label,
                    source_sentence=src_sent,
                    cosine_score=round(float(score), 3),
                    rerank_score=round(rerank_score, 3) if rerank_score else None,
                    is_paraphrase=is_para,
                ))

        results.sort(key=lambda x: x.cosine_score, reverse=True)
        return results

    # ------------------------------------------------------------------
    # Direct comparison (two texts, no index)
    # ------------------------------------------------------------------

    def compare(self, text_a: str, text_b: str) -> dict:
        """
        Compute maximum sentence-level cosine similarity between two texts.
        """
        self._load_models()
        sents_a = [s for s in self._split_sentences(text_a) if len(s.split()) >= 8]
        sents_b = [s for s in self._split_sentences(text_b) if len(s.split()) >= 8]
        if not sents_a or not sents_b:
            return {"max_cosine": 0.0, "mean_cosine": 0.0, "flagged": False}

        vecs_a = self._model.encode(sents_a, normalize_embeddings=True,
                                    show_progress_bar=False)
        vecs_b = self._model.encode(sents_b, normalize_embeddings=True,
                                    show_progress_bar=False)
        sim_matrix = np.dot(vecs_a, vecs_b.T)

        max_sim = float(sim_matrix.max())
        mean_sim = float(sim_matrix.mean())
        return {
            "max_cosine": round(max_sim, 3),
            "mean_cosine": round(mean_sim, 3),
            "flagged": max_sim >= self.cosine_threshold,
        }

    # ------------------------------------------------------------------

    def _split_sentences(self, text: str) -> list[str]:
        import re
        parts = re.split(r"(?<=[.!?])\s+(?=[A-Z])", text)
        return [p.strip() for p in parts if p.strip()]
