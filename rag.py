import math
import re
from pathlib import Path
from typing import Optional


class BM25SearchEngine:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.documents: list[tuple[str, str]] = []
        self.doc_tokens: list[list[str]] = []
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0
        self.num_docs: int = 0
        self.inverted_index: dict[str, set[int]] = {}
        self.doc_freqs: dict[str, int] = {}

    def _tokenize(self, text: str) -> list[str]:
        return [
            w for w in re.split(r"[^a-zA-Zа-яА-ЯёЁ0-9]+", text.lower())
            if len(w) > 1
        ]

    def add_document(self, source: str, text: str) -> None:
        idx = len(self.documents)
        self.documents.append((source, text))
        tokens = self._tokenize(text)
        self.doc_tokens.append(tokens)
        self.doc_lengths.append(len(tokens))

        for token in set(tokens):
            if token not in self.inverted_index:
                self.inverted_index[token] = set()
            self.inverted_index[token].add(idx)

    def _compute_stats(self) -> None:
        n = len(self.documents)
        if n == 0:
            self.avg_doc_length = 0.0
            self.num_docs = 0
            return
        self.avg_doc_length = sum(self.doc_lengths) / n
        self.num_docs = n
        self.doc_freqs = {
            term: len(docs) for term, docs in self.inverted_index.items()
        }

    def index_directory(
        self, dir_path: Path, extensions: Optional[list[str]] = None
    ) -> int:
        if extensions is None:
            extensions = [".txt", ".md"]

        count = 0
        for file_path in dir_path.glob("**/*"):
            if file_path.is_file() and file_path.suffix in extensions:
                try:
                    text = file_path.read_text(encoding="utf-8")
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    for para in paragraphs:
                        self.add_document(file_path.name, para)
                        count += 1
                except Exception:
                    pass

        self._compute_stats()
        return count

    def _ensure_stats(self) -> None:
        if self.num_docs == 0 and len(self.documents) > 0:
            self._compute_stats()

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        self._ensure_stats()
        query_tokens = self._tokenize(query)
        if not query_tokens or self.num_docs == 0:
            return []

        scores = [0.0] * self.num_docs

        for qt in query_tokens:
            if qt not in self.inverted_index:
                continue

            n_qt = self.doc_freqs.get(qt, 0)
            idf = math.log((self.num_docs - n_qt + 0.5) / (n_qt + 0.5) + 1)

            for doc_idx in self.inverted_index[qt]:
                tf = self.doc_tokens[doc_idx].count(qt)
                doc_len = self.doc_lengths[doc_idx]
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (
                    1 - self.b + self.b * doc_len / self.avg_doc_length
                )
                scores[doc_idx] += idf * numerator / denominator

        scored = [(i, scores[i]) for i in range(len(scores)) if scores[i] > 0]
        scored.sort(key=lambda x: x[1], reverse=True)

        results = []
        for doc_idx, score in scored[:top_k]:
            source, text = self.documents[doc_idx]
            results.append({"source": source, "text": text, "score": round(score, 4)})

        return results
