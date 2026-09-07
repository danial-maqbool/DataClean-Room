"""CPU semantic ranking with a locally fitted latent semantic analysis model.

LSA learns word co-occurrence in the selected corpus. It is not a pretrained
language model and it does not invent answers. Scores are similarities, not
probabilities. A local Sentence Transformer can be selected explicitly.
"""

from __future__ import annotations
import hashlib
import json
import os
import re
import threading
from pathlib import Path
from .safety import InputError, checked_path

MAX_CHUNKS = 5000
MAX_CHARS = 250_000


def chunks(text: str, size=1800, overlap=180):
    text = str(text)[:MAX_CHARS]
    for start in range(0, len(text), size - overlap):
        part = text[start : start + size]
        if part.strip():
            yield start, part


class SemanticModel:
    def __init__(self, texts: list[str], model_path: str = ""):
        if not texts or len(texts) > MAX_CHUNKS:
            raise InputError("Select a corpus with 1 to 5,000 text chunks.")
        self.texts = texts
        self.path = model_path
        self.encoder = None
        self.reducer = None
        if model_path:
            directory = checked_path(model_path, directory=True)
            import json

            manifest = directory / "modules.json"
            if not manifest.is_file() or manifest.stat().st_size > 100000:
                raise InputError("Choose a local Sentence Transformers model folder.")
            modules = json.loads(manifest.read_text(encoding="utf-8"))
            allowed = {
                "sentence_transformers.models.Transformer",
                "sentence_transformers.models.Pooling",
                "sentence_transformers.models.Normalize",
            }
            if not isinstance(modules, list) or any(
                not isinstance(m, dict) or m.get("type") not in allowed for m in modules
            ):
                raise InputError(
                    "Only Transformer, Pooling, and Normalize model modules are accepted."
                )
            if not any(directory.rglob("*.safetensors")):
                raise InputError(
                    "Use local safetensors model weights. Pickle model files are not loaded."
                )
            if any(p.is_symlink() for p in directory.rglob("*")):
                raise InputError("Model files must be real local files, not links.")
            os.environ["HF_HUB_OFFLINE"] = "1"
            os.environ["TRANSFORMERS_OFFLINE"] = "1"
            os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise InputError(
                    "Install requirements-neural.txt before selecting a neural model."
                ) from exc
            self.encoder = SentenceTransformer(
                str(directory),
                device="cpu",
                local_files_only=True,
                trust_remote_code=False,
                model_kwargs={"use_safetensors": True},
            )
            self.vectors = self.encoder.encode(
                texts, normalize_embeddings=True, show_progress_bar=False, batch_size=16
            )
            self.method = "Local neural embeddings"
            self.dimension = int(self.vectors.shape[1])
        else:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.decomposition import TruncatedSVD
            from sklearn.preprocessing import normalize

            self.vectorizer = TfidfVectorizer(
                max_features=20000,
                sublinear_tf=True,
                strip_accents="unicode",
                ngram_range=(1, 2),
                token_pattern=r"(?u)\b\w\w+\b",
            )
            try:
                matrix = self.vectorizer.fit_transform(texts)
            except ValueError as exc:
                raise InputError(
                    "The selected documents contain no searchable word tokens."
                ) from exc
            dimension = min(96, max(1, len(texts) - 1), max(1, matrix.shape[1] - 1))
            if dimension >= 2:
                self.reducer = TruncatedSVD(
                    n_components=dimension,
                    algorithm="randomized",
                    n_iter=5,
                    random_state=0,
                )
                self.vectors = normalize(self.reducer.fit_transform(matrix))
                self.method = "Local latent semantic analysis"
            else:
                self.vectors = normalize(matrix)
                self.method = "Local TF-IDF (corpus too small for LSA)"
            self.dimension = dimension

    def scores(self, query: str) -> list[float]:
        if not isinstance(query, str) or not query.strip() or len(query) > 4000:
            raise InputError("Enter a search query with 1 to 4,000 characters.")
        import numpy as np

        if self.encoder:
            q = self.encoder.encode(
                [query], normalize_embeddings=True, show_progress_bar=False
            )
            result = self.vectors @ q[0]
        else:
            from sklearn.preprocessing import normalize

            q = self.vectorizer.transform([query])
            if self.reducer:
                q = normalize(self.reducer.transform(q))
                result = self.vectors @ q[0]
            else:
                result = (self.vectors @ q.T).toarray().ravel()
        return [
            round(max(-1.0, min(1.0, float(v))), 6) for v in np.asarray(result).ravel()
        ]


class SearchCache:
    """Cache one corpus model in RAM. Never write pickle or clear-text vectors."""

    def __init__(self):
        self.lock = threading.RLock()
        self.fingerprint = ""
        self.model = None
        self.records = []

    def search(
        self, records: list[dict], query: str, *, model_path="", limit=100, minimum=0.05
    ):
        if not records:
            return {"results": [], "engine": "Local semantic search", "chunks": 0}
        fingerprint = hashlib.sha256(model_path.encode())
        expanded = []
        for record in records:
            fingerprint.update(
                json.dumps(
                    [
                        record.get("id", record.get("source", "")),
                        record.get("name", ""),
                        record.get("text", ""),
                    ],
                    ensure_ascii=False,
                ).encode("utf-8")
            )
            for offset, part in chunks(
                str(record.get("name", "")) + "\n" + str(record.get("text", ""))
            ):
                expanded.append({"record": record, "text": part, "offset": offset})
                if len(expanded) > MAX_CHUNKS:
                    raise InputError(
                        "Semantic search reached 5,000 chunks. Select a smaller folder or use keyword search."
                    )
        if not expanded:
            return {"results": [], "engine": "Local semantic search", "chunks": 0}
        fingerprint = fingerprint.hexdigest()
        with self.lock:
            if self.model is None or fingerprint != self.fingerprint:
                self.model = SemanticModel([x["text"] for x in expanded], model_path)
                self.fingerprint = fingerprint
            scores = self.model.scores(query)
            best = {}
            for part, score in zip(expanded, scores):
                if score < minimum:
                    continue
                row = part["record"]
                ident = row.get("id", row.get("source", ""))
                if ident not in best or score > best[ident]["semantic_score"]:
                    best[ident] = {
                        **{k: v for k, v in row.items() if k != "text"},
                        "semantic_score": score,
                        "snippet": part["text"][:320],
                        "text_length": len(str(row.get("text", ""))),
                        "chunk_offset": part["offset"],
                        "match_reason": "Local model similarity. Check the source text.",
                    }
            hits = sorted(
                best.values(),
                key=lambda r: (-r["semantic_score"], str(r.get("id", ""))),
            )[:limit]
            return {
                "results": hits,
                "engine": self.model.method,
                "dimensions": self.model.dimension,
                "chunks": len(expanded),
                "suggestions": [],
                "limit": limit,
                "limited": len(best) > limit,
                "score_note": "Cosine similarity, not a confidence or probability.",
            }


def extractive_summary(text: str, sentences: int = 3) -> str:
    """Rank source sentences and return only existing sentences, in source order."""
    if not isinstance(sentences, int) or not 1 <= sentences <= 10:
        raise InputError("Choose 1 to 10 summary sentences.")
    parts = [
        p.strip()
        for p in re.split(r"(?<=[.!?])\s+|\n+", str(text)[:MAX_CHARS])
        if len(p.strip()) > 15
    ][:300]
    if len(parts) <= sentences:
        return "\n".join(parts)
    from sklearn.feature_extraction.text import TfidfVectorizer
    import numpy as np

    try:
        matrix = TfidfVectorizer().fit_transform(parts)
    except ValueError:
        return "\n".join(parts[:sentences])
    centroid = matrix.mean(axis=0)
    scores = np.asarray(matrix @ centroid.T).ravel()
    selected = sorted(
        sorted(range(len(parts)), key=lambda i: (-scores[i], i))[:sentences]
    )
    return "\n".join(parts[i] for i in selected)
