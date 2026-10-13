"""
GraphRAG store: Entity Matching -> Graph Traversal -> Triple Textualization.

Ưu tiên kết nối Neo4j thật (Community local qua Docker). Nếu không kết nối được
và bật GRAPH_INMEMORY_FALLBACK, hệ thống tự dùng graph in-memory từ graph_seed để
không bao giờ gãy lúc demo. Dữ liệu là đồ thị tự curate quanh Đái tháo đường +
ICD-10 (miễn phí), không dùng SNOMED/UMLS.

Pipeline:
  1. match_entities(query): nhận diện thực thể y khoa trong câu hỏi.
  2. traverse(entities):     lấy các triple liên quan (đa bước 1 hop).
  3. textualize(triples):    chuyển triple thành câu tự nhiên nạp vào prompt.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core import config
from core import graph_seed


@dataclass
class GraphContext:
    entities: List[str] = field(default_factory=list)
    triples: List[Tuple[str, str, str]] = field(default_factory=list)
    text: str = ""
    backend: str = "none"       # "neo4j" | "in-memory" | "none"
    available: bool = False


class GraphStore:
    def __init__(self):
        self._driver = None
        self._backend = "none"
        self._lock = threading.Lock()
        self._initialized = False

    # ---- init / connect ------------------------------------------------
    def _ensure_init(self):
        if self._initialized:
            return
        with self._lock:
            if self._initialized:
                return
            if not config.ENABLE_GRAPH:
                self._backend = "none"
                self._initialized = True
                return
            self._try_connect_neo4j()
            if self._driver is None and config.GRAPH_INMEMORY_FALLBACK:
                self._backend = "in-memory"
                print("[Graph] Dùng Knowledge Graph in-memory (fallback).")
            self._initialized = True

    def _try_connect_neo4j(self):
        try:
            from neo4j import GraphDatabase

            driver = GraphDatabase.driver(
                config.NEO4J_URI,
                auth=(config.NEO4J_USER, config.NEO4J_PASSWORD),
            )
            driver.verify_connectivity()
            # Kiểm tra đã có dữ liệu chưa.
            with driver.session(database=config.NEO4J_DATABASE) as session:
                count = session.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
            if count == 0:
                print("[Graph] ⚠️ Neo4j rỗng — hãy chạy scripts/build_graph.py. Tạm fallback in-memory.")
                driver.close()
                return
            self._driver = driver
            self._backend = "neo4j"
            print(f"[Graph] ✅ Kết nối Neo4j ({count} thực thể).")
        except Exception as exc:  # pragma: no cover - phụ thuộc môi trường
            print(f"[Graph] ⚠️ Không kết nối được Neo4j ({exc}).")
            self._driver = None

    # ---- entity matching ----------------------------------------------
    @staticmethod
    def _match_in_text(query: str) -> List[str]:
        q = (query or "").lower()
        matched = []
        for name, meta in graph_seed.ENTITIES.items():
            names = [name.lower()] + [s.lower() for s in meta.get("synonyms", [])]
            icd = meta.get("icd10")
            if icd:
                names.append(icd.lower())
            if any(n in q for n in names):
                matched.append(name)
        return matched

    def match_entities(self, query: str) -> List[str]:
        return self._match_in_text(query)

    # ---- traversal -----------------------------------------------------
    def _traverse_inmemory(self, entities: List[str]) -> List[Tuple[str, str, str]]:
        ent_set = set(entities)
        found = []
        for s, r, o in graph_seed.TRIPLES:
            if s in ent_set or o in ent_set:
                found.append((s, r, o))
        return found[: config.GRAPH_MAX_TRIPLES]

    def _traverse_neo4j(self, entities: List[str]) -> List[Tuple[str, str, str]]:
        triples = []
        cypher = (
            "MATCH (a:Entity)-[rel]->(b:Entity) "
            "WHERE a.name IN $names OR b.name IN $names "
            "RETURN a.name AS s, rel.label AS r, b.name AS o "
            "LIMIT $limit"
        )
        try:
            with self._driver.session(database=config.NEO4J_DATABASE) as session:
                for rec in session.run(cypher, names=entities, limit=config.GRAPH_MAX_TRIPLES):
                    triples.append((rec["s"], rec["r"], rec["o"]))
        except Exception as exc:  # pragma: no cover
            print(f"[Graph] ⚠️ Lỗi truy vấn Neo4j ({exc}).")
        return triples

    # ---- textualize ----------------------------------------------------
    @staticmethod
    def textualize(triples: List[Tuple[str, str, str]]) -> str:
        if not triples:
            return ""
        lines = [f"- {s} {r} {o}." for s, r, o in triples]
        return "Tri thức từ Knowledge Graph y khoa:\n" + "\n".join(lines)

    # ---- public --------------------------------------------------------
    def query(self, query: str) -> GraphContext:
        self._ensure_init()
        if self._backend == "none":
            return GraphContext(backend="none", available=False)

        entities = self.match_entities(query)
        if not entities:
            return GraphContext(entities=[], backend=self._backend, available=True)

        if self._backend == "neo4j":
            triples = self._traverse_neo4j(entities)
            if not triples:  # DB có thể thiếu quan hệ -> bù bằng seed
                triples = self._traverse_inmemory(entities)
        else:
            triples = self._traverse_inmemory(entities)

        return GraphContext(
            entities=entities,
            triples=triples,
            text=self.textualize(triples),
            backend=self._backend,
            available=True,
        )

    def close(self):
        if self._driver is not None:
            self._driver.close()
            self._driver = None


# Singleton
_store: Optional[GraphStore] = None
_store_lock = threading.Lock()


def get_graph_store() -> GraphStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = GraphStore()
    return _store
