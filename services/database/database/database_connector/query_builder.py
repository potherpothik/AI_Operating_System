import re
from sqlalchemy import text

_READ_PREFIX = re.compile(r"^\s*SELECT\b", re.IGNORECASE)
_WRITE_PREFIX = re.compile(r"^\s*(UPDATE|DELETE|INSERT)\b", re.IGNORECASE)
_DDL_PREFIX = re.compile(r"^\s*(ALTER|CREATE|DROP|TRUNCATE)\b", re.IGNORECASE)

# Defense in depth on top of structural parameterization: reject anything
# that looks like a stacked statement or a comment-based truncation
# attempt, the classic injection vectors even a parameterized query
# shouldn't need to tolerate in a single template.
_SUSPICIOUS_PATTERNS = [
    re.compile(r";\s*\S"),  # a second statement after a semicolon
    re.compile(r"--"),
    re.compile(r"/\*"),
]


class UnparameterizedQuery(Exception):
    pass


class UnsupportedStatement(Exception):
    pass


def classify(sql_template: str) -> str:
    if _DDL_PREFIX.match(sql_template):
        return "ddl"
    if _WRITE_PREFIX.match(sql_template):
        return "write"
    if _READ_PREFIX.match(sql_template):
        return "read"
    raise UnsupportedStatement(f"cannot classify statement: {sql_template[:80]!r}")


def build(sql_template: str, params: dict):
    """
    Structural enforcement, not a naming convention: the caller supplies a
    template with named bind parameters (:name) and a SEPARATE params
    dict — there is no code path that accepts one pre-interpolated
    string. SQLAlchemy's text().bindparams() sends the SQL text and the
    parameter values to the driver separately, which is what actually
    prevents injection (the same structural-separation principle Prompt
    Builder uses for untrusted context in Phase 4 — not string escaping,
    architecture).
    """
    for pattern in _SUSPICIOUS_PATTERNS:
        if pattern.search(sql_template):
            raise UnparameterizedQuery(f"template contains a disallowed pattern ({pattern.pattern!r})")

    placeholders = set(re.findall(r":(\w+)\b", sql_template))
    missing = placeholders - set(params.keys())
    if missing:
        raise UnparameterizedQuery(f"template references placeholders with no matching params: {sorted(missing)}")

    return text(sql_template).bindparams(**params)
