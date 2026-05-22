from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.core.config import settings, get_settings

logger = get_logger(__name__)

@dataclass
class Node:
    node_id: str
    label: str
    node_type: str
    properties: dict[str, Any] = field(default_factory=dict)

@dataclass
class Edge:
    source: str
    target: str
    relationship: str
    properties: dict[str, Any] = field(default_factory=dict)

@dataclass
class GraphResult:
    nodes: list[Node] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

class GraphIntelligence:
    """Graph-based intelligence for relationship mapping and link analysis."""

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: list[Edge] = []

    def add_entity(self, entity_id: str, label: str, entity_type: str, properties: dict[str, Any] | None = None) -> None:
        if entity_id not in self._nodes:
            self._nodes[entity_id] = Node(
                node_id=entity_id,
                label=label,
                node_type=entity_type,
                properties=properties or {},
            )

    def add_relationship(self, source: str, target: str, relationship: str, properties: dict[str, Any] | None = None) -> None:
        self._edges.append(Edge(
            source=source,
            target=target,
            relationship=relationship,
            properties=properties or {},
        ))

    def find_paths(self, start: str, end: str, max_depth: int = 5) -> list[list[str]]:
        adj: dict[str, list[str]] = {}
        for edge in self._edges:
            adj.setdefault(edge.source, []).append(edge.target)
            adj.setdefault(edge.target, []).append(edge.source)

        paths = []
        queue = [(start, [start])]
        while queue:
            current, path = queue.pop(0)
            if len(path) > max_depth:
                continue
            if current == end and len(path) > 1:
                paths.append(path)
                continue
            for neighbor in adj.get(current, []):
                if neighbor not in path:
                    queue.append((neighbor, path + [neighbor]))
        return paths

    def find_connected_nodes(self, node_id: str, depth: int = 1) -> GraphResult:
        result_nodes = {}
        result_edges = []

        if node_id in self._nodes:
            result_nodes[node_id] = self._nodes[node_id]

        for edge in self._edges:
            if edge.source == node_id or edge.target == node_id:
                if edge.source in self._nodes:
                    result_nodes[edge.source] = self._nodes[edge.source]
                if edge.target in self._nodes:
                    result_nodes[edge.target] = self._nodes[edge.target]
                result_edges.append(edge)

        if depth > 1:
            connected_ids = set(result_nodes.keys())
            for edge in self._edges:
                if edge.source in connected_ids or edge.target in connected_ids:
                    if edge.source in self._nodes:
                        result_nodes[edge.source] = self._nodes[edge.source]
                    if edge.target in self._nodes:
                        result_nodes[edge.target] = self._nodes[edge.target]
                    if edge not in result_edges:
                        result_edges.append(edge)

        return GraphResult(
            nodes=list(result_nodes.values()),
            edges=result_edges,
            metadata={"query_node": node_id, "depth": depth},
        )

    def get_influence_score(self, node_id: str) -> float:
        connections = 0
        for edge in self._edges:
            if edge.source == node_id or edge.target == node_id:
                connections += 1
        return connections

    def get_all_paths_from(self, node_id: str, max_depth: int = 3) -> list[list[str]]:
        adj: dict[str, list[str]] = {}
        for edge in self._edges:
            adj.setdefault(edge.source, []).append(edge.target)
            adj.setdefault(edge.target, []).append(edge.source)

        all_paths = []
        stack = [(node_id, [node_id])]
        while stack:
            current, path = stack.pop()
            if len(path) > 1:
                all_paths.append(path)
            if len(path) >= max_depth:
                continue
            for neighbor in adj.get(current, []):
                if neighbor not in path:
                    stack.append((neighbor, path + [neighbor]))
        return all_paths

    def export_neo4j_cypher(self) -> list[str]:
        """Generate Cypher MERGE statements for visual export ONLY.

        SECURITY: The returned strings interpolate node/edge values directly into
        Cypher source. They are SAFE to display, log or attach to a report, but
        MUST NOT be sent to a live Neo4j driver — that would constitute a Cypher
        injection sink. To persist a graph, use the official driver with
        parameterized queries: ``session.run("MERGE (n {id:$id})", id=node.node_id)``.

        Labels and relationship types are constrained to ``[A-Za-z0-9_]`` to
        avoid breaking out of identifier position even in the export string.
        """
        import re as _re

        def _safe_ident(value: str, fallback: str) -> str:
            cleaned = _re.sub(r"[^A-Za-z0-9_]", "", value or "")
            return cleaned or fallback

        def _quote(value: str) -> str:
            # Escape single-quotes and backslashes so the export string remains
            # syntactically valid even if values contain quotes.
            return value.replace("\\", "\\\\").replace("'", "\\'")

        statements = []
        for node in self._nodes.values():
            label = _safe_ident(node.node_type, "Node")
            props = ", ".join(
                f"{_safe_ident(k, 'p')}: '{_quote(v)}'"
                for k, v in node.properties.items()
                if isinstance(v, str)
            )
            stmt = (
                f"MERGE (n:{label} {{id: '{_quote(node.node_id)}', "
                f"label: '{_quote(node.label)}'{', ' + props if props else ''}}})"
            )
            statements.append(stmt)

        for edge in self._edges:
            rel = _safe_ident(edge.relationship, "RELATED_TO")
            props = ", ".join(
                f"{_safe_ident(k, 'p')}: '{_quote(v)}'"
                for k, v in edge.properties.items()
                if isinstance(v, str)
            )
            extra_props = (", " + props) if props else ""
            stmt = (
                f"MATCH (a {{id: '{_quote(edge.source)}'}}), "
                f"(b {{id: '{_quote(edge.target)}'}}) "
                f"MERGE (a)-[r:{rel} {{{extra_props}}}]->(b)"
            )
            statements.append(stmt)

        return statements

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [
                {"id": n.node_id, "label": n.label, "type": n.node_type, "properties": n.properties}
                for n in self._nodes.values()
            ],
            "edges": [
                {"source": e.source, "target": e.target, "relationship": e.relationship, "properties": e.properties}
                for e in self._edges
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GraphIntelligence":
        gi = cls()
        for node_data in data.get("nodes", []):
            gi.add_entity(
                node_data["id"],
                node_data["label"],
                node_data["type"],
                node_data.get("properties"),
            )
        for edge_data in data.get("edges", []):
            gi.add_relationship(
                edge_data["source"],
                edge_data["target"],
                edge_data["relationship"],
                edge_data.get("properties"),
            )
        return gi

graph_intel = GraphIntelligence()
