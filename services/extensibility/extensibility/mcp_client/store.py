import datetime
from sqlalchemy.orm import Session

from extensibility.mcp_client.models import McpServer, McpInvocation


def _now():
    return datetime.datetime.now(datetime.timezone.utc)


def create_server(db: Session, name: str, url: str, description: str, local_only: bool, tool_schemas: dict, registered_by: str, approval_id: str) -> McpServer:
    server = McpServer(
        name=name, url=url, description=description, local_only=local_only,
        tool_schemas=tool_schemas or {}, registered_by=registered_by, approval_id=approval_id,
    )
    db.add(server)
    db.commit()
    db.refresh(server)
    return server


def get_server(db: Session, server_id: str) -> McpServer | None:
    return db.query(McpServer).filter(McpServer.id == server_id).first()


def get_server_by_name(db: Session, name: str) -> McpServer | None:
    return db.query(McpServer).filter(McpServer.name == name).first()


def list_servers(db: Session) -> list[McpServer]:
    return db.query(McpServer).order_by(McpServer.registered_at.desc()).all()


def activate_server(db: Session, server: McpServer) -> McpServer:
    server.status = "active"
    server.decided_at = _now()
    db.commit()
    db.refresh(server)
    return server


def reject_server(db: Session, server: McpServer) -> McpServer:
    server.status = "rejected"
    server.decided_at = _now()
    db.commit()
    db.refresh(server)
    return server


def disable_server(db: Session, server: McpServer) -> McpServer:
    server.status = "disabled"
    db.commit()
    db.refresh(server)
    return server


def record_invocation(db: Session, server_id: str, tool_name: str, params: dict, result: dict, status: str,
                       reason: str, capability: str, task_id: str, correlation_id: str) -> McpInvocation:
    row = McpInvocation(
        server_id=server_id, tool_name=tool_name, params=params, result=result, status=status,
        reason=reason, capability=capability, task_id=task_id, correlation_id=correlation_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
