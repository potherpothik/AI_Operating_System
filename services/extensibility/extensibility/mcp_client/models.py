import uuid
import datetime
from sqlalchemy import Column, String, Boolean, DateTime, JSON, Text

from extensibility.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


class McpServer(Base):
    """
    A registered external tool source. `local_only=False` (a remote
    server) always requires explicit human approval before it can ever
    be invoked — the doc's "explicit approval for any remote server," a
    stricter default than local-only servers, which are still
    approval-gated but not singled out with the same suspicion an
    arbitrary remote endpoint deserves.
    """

    __tablename__ = "mcp_server"

    id = Column(String, primary_key=True, default=_uuid)
    name = Column(String, nullable=False, unique=True)
    url = Column(String, nullable=False)
    description = Column(Text, default="")
    local_only = Column(Boolean, default=True)
    tool_schemas = Column(JSON, default=dict)  # {tool_name: {field: "str"|"float"|"list"|"optional_str"}}
    status = Column(String, default="pending_approval")  # pending_approval | active | disabled | rejected
    registered_by = Column(String, nullable=False)
    approval_id = Column(String, nullable=True)
    registered_at = Column(DateTime(timezone=True), default=_now)
    decided_at = Column(DateTime(timezone=True), nullable=True)


class McpInvocation(Base):
    """
    Every tool call, regardless of outcome — the audit trail behind
    "MCP Client is a new tool source, not a new trust boundary": each
    call is authorized, attempted, and logged the same as any other
    tool-shaped action in this system.
    """

    __tablename__ = "mcp_invocation"

    id = Column(String, primary_key=True, default=_uuid)
    server_id = Column(String, nullable=False)
    tool_name = Column(String, nullable=False)
    params = Column(JSON, default=dict)
    result = Column(JSON, nullable=True)
    status = Column(String, nullable=False)  # completed | failed | denied
    reason = Column(Text, default="")
    capability = Column(String, nullable=False)
    task_id = Column(String, nullable=True)
    correlation_id = Column(String, default="")
    ts = Column(DateTime(timezone=True), default=_now)
