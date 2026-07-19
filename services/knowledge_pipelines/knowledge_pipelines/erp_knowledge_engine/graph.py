class NoCurrentSnapshot(Exception):
    pass


def tables_referencing(tables: dict, target_table: str) -> list[dict]:
    """Precise relational query — 'what tables reference this one' —
    exactly the question the Phase 9 doc names as one semantic similarity
    search answers poorly, hence a dedicated structured query mode
    alongside Vector Search rather than folding everything into it."""
    referencing = []
    for table_name, info in tables.items():
        for fk in info.get("foreign_keys", []):
            if fk["references_table"] == target_table:
                referencing.append({"table": table_name, "via_columns": fk["columns"]})
    return referencing


def references_of(tables: dict, table_name: str) -> list[dict]:
    info = tables.get(table_name)
    if not info:
        return []
    return [
        {"table": fk["references_table"], "via_columns": fk["columns"]}
        for fk in info.get("foreign_keys", [])
    ]


def full_graph(tables: dict) -> dict:
    """Nodes = tables, edges = FK relationships — a genuine, precise
    relationship graph derived from the real synced schema, not inferred
    or approximated."""
    nodes = list(tables.keys())
    edges = []
    for table_name, info in tables.items():
        for fk in info.get("foreign_keys", []):
            edges.append({"from": table_name, "to": fk["references_table"], "via": fk["columns"]})
    return {"nodes": nodes, "edges": edges}
