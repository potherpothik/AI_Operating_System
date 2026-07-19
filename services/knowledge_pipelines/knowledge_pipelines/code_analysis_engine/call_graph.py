def resolve_edges(symbols_by_file: dict, calls_by_symbol_id: dict) -> list[dict]:
    """
    Intra-file call resolution: for each caller's raw call-name list
    (from parsers/python.py), looks for a symbol with a matching `name`
    in the SAME file and records an edge. A call to something not
    defined in that file (an import, a builtin, a stdlib function) is
    silently not an edge — not an error, just outside this first
    version's scope (models.py's CallEdge docstring).
    """
    edges = []
    for file_symbols in symbols_by_file.values():
        by_name = {}
        for sym in file_symbols:
            by_name.setdefault(sym["name"], []).append(sym)

        for caller in file_symbols:
            for call_name in calls_by_symbol_id.get(caller["id"], []):
                for callee in by_name.get(call_name, []):
                    if callee["id"] == caller["id"]:
                        continue  # not tracking direct self-recursion as an edge
                    edges.append({"caller_symbol_id": caller["id"], "callee_symbol_id": callee["id"]})
    return edges


def callers_of(symbol_id: str, edges: list[dict]) -> list[str]:
    return [e["caller_symbol_id"] for e in edges if e["callee_symbol_id"] == symbol_id]


def callees_of(symbol_id: str, edges: list[dict]) -> list[str]:
    return [e["callee_symbol_id"] for e in edges if e["caller_symbol_id"] == symbol_id]


def full_graph(symbols: list[dict], edges: list[dict]) -> dict:
    """Nodes = symbol qualified_names, edges = resolved call references —
    same nodes/edges shape as erp_knowledge_engine/graph.py's full_graph,
    the pattern this phase reuses rather than inventing a new one."""
    by_id = {s["id"]: s["qualified_name"] for s in symbols}
    nodes = [s["qualified_name"] for s in symbols]
    graph_edges = [
        {"from": by_id.get(e["caller_symbol_id"], e["caller_symbol_id"]), "to": by_id.get(e["callee_symbol_id"], e["callee_symbol_id"])}
        for e in edges
    ]
    return {"nodes": nodes, "edges": graph_edges}
