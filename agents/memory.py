"""
Memory Utilities
~~~~~~~~~~~~~~~~
参考 BookWorld 的记忆拆分结构：
1. HistoryManager: 负责短期流水（recent history）
2. BranchVectorMemory: 负责长期语义检索（long-term memory）
3. MemoryManager: 组合式接口，统一封装长短期读写

针对 Visual Novel 的扩展：
- 每条记忆带 node_id，用于分支图的祖先过滤，避免平行分支串台。
- 长期记忆优先落盘到 ChromaDB（默认 data/chroma）。
- ChromaDB 不可用时回退到进程内哈希向量表。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Set
import copy
import hashlib
import json
import logging
import os
import re
import threading

import numpy as np


EmbeddingFn = Callable[[str], np.ndarray]
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _normalize_collection_name(name: str) -> str:
    """将 collection 名规范化为 Chroma 友好形式。"""
    clean = re.sub(r"[^a-zA-Z0-9_-]", "_", str(name or "memory"))
    clean = clean.strip("_") or "memory"
    if len(clean) < 3:
        clean = (clean + "_mem")[:3]
    if len(clean) > 63:
        clean = clean[:63]
    return clean


def _stable_record_id(node_id: str, owner_id: str, text: str) -> str:
    raw = f"{node_id}|{owner_id}|{text}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"mem_{digest}"


def _normalize_text(text: str) -> str:
    text = (text or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def _hash_embedding(text: str, dim: int = 512, ngram: int = 3) -> np.ndarray:
    """无外部依赖的确定性哈希向量。

    采用字符 n-gram hashing，兼容中英文混合文本。
    """
    normalized = _normalize_text(text)
    vec = np.zeros(dim, dtype=np.float32)
    if not normalized:
        return vec

    if len(normalized) < ngram:
        grams = [normalized]
    else:
        grams = [normalized[i : i + ngram] for i in range(len(normalized) - ngram + 1)]

    for gram in grams:
        digest = hashlib.sha256(gram.encode("utf-8")).hexdigest()
        idx = int(digest[:8], 16) % dim
        sign = 1.0 if int(digest[8:10], 16) % 2 == 0 else -1.0
        vec[idx] += sign

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec


def default_hash_embedding(text: str, dim: int = 512, ngram: int = 3) -> np.ndarray:
    """对外暴露的默认哈希 embedding。"""
    return _hash_embedding(text=text, dim=dim, ngram=ngram)


@dataclass
class HistoryRecord:
    node_id: str
    detail: str
    role_code: str = ""

    def to_dict(self) -> Dict[str, Any]:
        # 极简外层：仅保留 content，其他字段全部放入 meta。
        return {
            "content": self.detail,
            "meta": {
                "source_node_id": self.node_id,
                "owner_id": self.role_code,
            },
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HistoryRecord":
        meta = data.get("meta", {}) or {}
        return cls(
            node_id=str(meta.get("source_node_id", "")),
            detail=str(data.get("content", "")),
            role_code=str(meta.get("owner_id", "")),
        )


class HistoryManager:
    """短期记忆管理器（BookWorld 风格）。"""

    def __init__(self, capacity: int = 5):
        self.capacity = max(1, capacity)
        self._records: List[HistoryRecord] = []
        self._lock = threading.Lock()

    def add_record(self, record: HistoryRecord) -> None:
        with self._lock:
            self._records.append(record)
            if len(self._records) > 10000:
                # 只做温和裁剪，避免分支并发时被 maxlen 互相挤压。
                self._records = self._records[-8000:]

    def get_recent_history(
        self,
        recent_k: int = 5,
        valid_node_ids: Optional[Set[str]] = None,
        role_code: Optional[str] = None,
    ) -> List[str]:
        with self._lock:
            records = list(self._records)

        if valid_node_ids is not None:
            records = [r for r in records if r.node_id in valid_node_ids]
        if role_code:
            records = [r for r in records if r.role_code == role_code]

        if recent_k > 0:
            records = records[-recent_k:]
        return [r.detail for r in records if r.detail]

    def get_complete_history(
        self,
        valid_node_ids: Optional[Set[str]] = None,
        role_code: Optional[str] = None,
    ) -> List[str]:
        return self.get_recent_history(recent_k=0, valid_node_ids=valid_node_ids, role_code=role_code)

    def clone(self) -> "HistoryManager":
        cloned = HistoryManager(capacity=self.capacity)
        with self._lock:
            cloned._records = copy.deepcopy(self._records)
        return cloned

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)

    def to_dict(self) -> List[Dict[str, Any]]:
        with self._lock:
            records = [record.to_dict() for record in self._records]
        return records

    def load_from_dict(self, rows: List[Dict[str, Any]]) -> None:
        rows = rows or []
        with self._lock:
            self._records = [HistoryRecord.from_dict(item) for item in rows if isinstance(item, dict)]

    @classmethod
    def from_dict(cls, rows: List[Dict[str, Any]], capacity: int = 5) -> "HistoryManager":
        manager = cls(capacity=capacity)
        manager.load_from_dict(rows)
        return manager


class BranchVectorMemory:
    """长期向量记忆（支持按分支祖先过滤）。"""

    def __init__(
        self,
        db_name: str,
        embedding_fn: Optional[EmbeddingFn] = None,
        persist_dir: Optional[str] = None,
    ):
        self.db_name = db_name
        self.embedding_fn = embedding_fn or _hash_embedding
        from .config import PathConfig
        default_chroma_dir = PathConfig.CHROMA_DIR or os.path.join(PROJECT_ROOT, "data", "chroma")
        self.persist_dir = persist_dir or default_chroma_dir
        self._lock = threading.Lock()
        self._collection = None
        self._fallback_records: Dict[str, Dict[str, Any]] = {}
        self._init_backend()

    def _init_backend(self) -> None:
        """初始化 ChromaDB 持久化后端；不可用时保留内存后端。"""
        try:
            import chromadb

            os.makedirs(self.persist_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=self.persist_dir)
            collection_name = _normalize_collection_name(self.db_name)
            self._collection = client.get_or_create_collection(name=collection_name)
            logger.info(f"✅ ChromaDB 已启用: {self.persist_dir} / {collection_name}")
        except Exception as e:
            self._collection = None
            logger.warning(f"⚠️ ChromaDB 不可用，长期记忆回退到内存: {e}")

    def _embed_text(self, text: str) -> np.ndarray:
        if self._collection is None:
            return _hash_embedding(text)
        try:
            vec_raw = self.embedding_fn(text)
            vec = np.asarray(vec_raw, dtype=np.float32)
            if vec.size == 0:
                return _hash_embedding(text)
            return vec
        except Exception:
            return _hash_embedding(text)

    def add_memory(
        self,
        node_id: str,
        text: str,
        owner_id: str = "",
        importance: float = 0.5,
    ) -> None:
        clean_text = (text or "").strip()
        if not clean_text:
            return

        vec = self._embed_text(clean_text)
        owner = str(owner_id or "")
        importance_value = float(max(0.0, min(1.0, importance)))
        record_id = _stable_record_id(node_id=node_id, owner_id=owner, text=clean_text)
        metadata = {
            "node_id": str(node_id),
            "owner_id": owner,
            "importance": importance_value,
        }
        if self._collection is None:
            with self._lock:
                self._fallback_records[record_id] = {
                    "document": clean_text,
                    "metadata": metadata,
                    "embedding": vec.tolist(),
                }
            return

        with self._lock:
            if hasattr(self._collection, "upsert"):
                self._collection.upsert(
                    ids=[record_id],
                    documents=[clean_text],
                    metadatas=[metadata],
                    embeddings=[vec.tolist()],
                )
            else:
                try:
                    self._collection.delete(ids=[record_id])
                except Exception:
                    pass
                self._collection.add(
                    ids=[record_id],
                    documents=[clean_text],
                    metadatas=[metadata],
                    embeddings=[vec.tolist()],
                )

    def _search_chroma(
        self,
        qvec: np.ndarray,
        valid_node_ids: Optional[Set[str]],
        top_k: int,
        owner_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        if self._collection is None:
            with self._lock:
                records = list(self._fallback_records.values())
            candidates: List[Dict[str, Any]] = []
            qnorm = float(np.linalg.norm(qvec))
            for record in records:
                meta = record["metadata"]
                node_id = str(meta.get("node_id", ""))
                doc_owner = str(meta.get("owner_id", ""))
                if valid_node_ids is not None and node_id not in valid_node_ids:
                    continue
                if owner_id and doc_owner != owner_id:
                    continue
                vector = np.asarray(record["embedding"], dtype=np.float32)
                denom = qnorm * float(np.linalg.norm(vector))
                similarity = float(np.dot(qvec, vector) / denom) if denom else 0.0
                importance = float(meta.get("importance", 0.5))
                candidates.append({
                    "node_id": node_id,
                    "text": str(record["document"]),
                    "owner_id": doc_owner,
                    "score": similarity * 0.8 + importance * 0.2,
                })
            candidates.sort(key=lambda item: item["score"], reverse=True)
            return candidates[:top_k]

        where_clause: Optional[Dict[str, Any]] = None
        if owner_id:
            where_clause = {"owner_id": owner_id}

        n_results = max(top_k * 8, 20)
        with self._lock:
            result = self._collection.query(
                query_embeddings=[qvec.tolist()],
                n_results=n_results,
                where=where_clause,
                include=["documents", "metadatas", "distances"],
            )

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        candidates: List[Dict[str, Any]] = []
        for doc, meta, dist in zip(documents, metadatas, distances):
            if not isinstance(meta, dict):
                continue
            node_id = str(meta.get("node_id", ""))
            if valid_node_ids is not None and node_id not in valid_node_ids:
                continue
            doc_owner = str(meta.get("owner_id", ""))
            if owner_id and doc_owner != owner_id:
                continue

            # Chroma cosine distance 越小越近，转为相似度分数。
            sim = 1.0 - float(dist)
            importance = float(meta.get("importance", 0.5))
            score = sim * 0.8 + importance * 0.2
            candidates.append(
                {
                    "node_id": node_id,
                    "text": str(doc or ""),
                    "owner_id": doc_owner,
                    "score": score,
                }
            )

        candidates.sort(key=lambda x: x["score"], reverse=True)
        return candidates[:top_k]

    def _print_search_results(
        self,
        query: str,
        owner_id: Optional[str],
        results: List[Dict[str, Any]],
    ) -> None:
        """打印每次长期记忆检索命中，便于调试。"""
        owner_label = owner_id if owner_id else "ALL"
        compact_query = (query or "").replace("\n", " ").strip()
        print(
            f"[MemorySearch][{self.db_name}] owner={owner_label} query={compact_query}",
            flush=True,
        )
        if not results:
            print("[MemorySearch] no long-term memory hit", flush=True)
            return

        for idx, item in enumerate(results, 1):
            print(
                (
                    f"[MemorySearch] #{idx} node={item.get('node_id', '')} "
                    f"owner={item.get('owner_id', '')} "
                    f"score={float(item.get('score', 0.0)):.4f} "
                    f"text={item.get('text', '')}"
                ),
                flush=True,
            )

    def search(
        self,
        query: str,
        valid_node_ids: Optional[Set[str]],
        top_k: int = 3,
        owner_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        if top_k <= 0:
            return []

        qvec = self._embed_text(query)

        results = self._search_chroma(
            qvec=qvec,
            valid_node_ids=valid_node_ids,
            top_k=top_k,
            owner_id=owner_id,
        )
        self._print_search_results(query=query, owner_id=owner_id, results=results)
        return results

    def to_dict(self) -> List[Dict[str, Any]]:
        if self._collection is None:
            with self._lock:
                fallback_records = list(self._fallback_records.values())
            return [
                {
                    "content": str(record["document"]),
                    "embedding": list(record["embedding"]),
                    "meta": {
                        "source_node_id": str(record["metadata"].get("node_id", "")),
                        "owner_id": str(record["metadata"].get("owner_id", "")),
                        "importance": float(record["metadata"].get("importance", 0.5)),
                    },
                }
                for record in fallback_records
            ]

        with self._lock:
            result = self._collection.get(include=["documents", "metadatas", "embeddings"])
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        embeddings = result.get("embeddings") or []
        records: List[Dict[str, Any]] = []
        for doc, meta, emb in zip(documents, metadatas, embeddings):
            meta = meta or {}
            records.append(
                {
                    "content": str(doc or ""),
                    "embedding": list(emb or []),
                    "meta": {
                        "source_node_id": str(meta.get("node_id", "")),
                        "owner_id": str(meta.get("owner_id", "")),
                        "importance": float(meta.get("importance", 0.5)),
                    },
                }
            )
        return records

    def load_from_dict(self, rows: List[Dict[str, Any]]) -> None:
        rows = rows or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            meta = row.get("meta", {}) or {}
            self.add_memory(
                node_id=str(meta.get("source_node_id", "")),
                text=str(row.get("content", "")),
                owner_id=str(meta.get("owner_id", "")),
                importance=float(meta.get("importance", 0.5)),
            )


class MemoryManager:
    """组合式记忆管理：短期 + 长期。"""

    def __init__(
        self,
        name: str,
        short_term_capacity: int = 5,
        embedding_fn: Optional[EmbeddingFn] = None,
        persist_dir: Optional[str] = None,
    ):
        self.name = name
        self.short_term = HistoryManager(capacity=short_term_capacity)
        self.long_term = BranchVectorMemory(
            db_name=name,
            embedding_fn=embedding_fn,
            persist_dir=persist_dir,
        )

    def add_short_term(
        self,
        node_id: str,
        detail: str,
        role_code: str = "",
    ) -> None:
        self.short_term.add_record(
            HistoryRecord(
                node_id=node_id,
                detail=detail,
                role_code=role_code,
            )
        )

    def add_long_term(
        self,
        node_id: str,
        text: str,
        owner_id: str = "",
        importance: float = 0.5,
    ) -> None:
        self.long_term.add_memory(
            node_id=node_id,
            text=text,
            owner_id=owner_id,
            importance=importance,
        )

    def build_context(
        self,
        query: str,
        valid_node_ids: Optional[Set[str]],
        short_k: int = 3,
        long_k: int = 3,
        short_title: str = "最近记录",
        long_title: str = "长期记忆",
        role_code: Optional[str] = None,
    ) -> str:
        short_items = self.short_term.get_recent_history(
            recent_k=short_k,
            valid_node_ids=valid_node_ids,
            role_code=role_code,
        )
        long_items = self.long_term.search(
            query=query,
            valid_node_ids=valid_node_ids,
            top_k=long_k,
            owner_id=role_code,
        )
        blocks: List[str] = []
        if long_items:
            lines = [f"- Node {item['node_id']}: {item['text']}" for item in long_items]
            blocks.append(f"【{long_title}】\n" + "\n".join(lines))
        if short_items:
            lines = [f"- {text}" for text in short_items]
            blocks.append(f"【{short_title}】\n" + "\n".join(lines))
        return "\n\n".join(blocks)

    def to_dict(self) -> Dict[str, Any]:
        # 统一命名：store_id / short_term_memory / long_term_memory
        return {
            "store_id": self.name,
            "short_term_memory": self.short_term.to_dict(),
            "long_term_memory": self.long_term.to_dict(),
        }

    def load_from_dict(self, data: Dict[str, Any]) -> None:
        self.name = str(data.get("store_id", self.name))
        short_term_data = data.get("short_term_memory", []) or []
        long_term_data = data.get("long_term_memory", []) or []
        self.short_term.load_from_dict(short_term_data)
        self.long_term.load_from_dict(long_term_data)

    def save_to_file(self, file_path: str) -> None:
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    def load_from_file(self, file_path: str) -> None:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("MemoryManager 存档格式错误：顶层应为对象")
        self.load_from_dict(data)
