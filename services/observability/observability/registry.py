import os

# The same *_URL env var convention every other service already uses to
# call its peers — Health Monitor and Metrics Dashboard share this one
# registry rather than each declaring their own copy (the design doc
# sketched a registry.py per module; a single shared one is the more
# honest reflection of "the same service list," not two copies that can
# drift apart).
SERVICES = [
    {"name": "governance", "url": os.environ.get("GOVERNANCE_URL", "http://localhost:8000")},
    {"name": "platform-spine", "url": os.environ.get("PLATFORM_URL", "http://localhost:8002")},
    {"name": "knowledge", "url": os.environ.get("KNOWLEDGE_URL", "http://localhost:8003")},
    {"name": "assembly", "url": os.environ.get("ASSEMBLY_URL", "http://localhost:8004")},
    {"name": "agents", "url": os.environ.get("AGENTS_URL", "http://localhost:8005")},
    {"name": "execution", "url": os.environ.get("EXECUTION_URL", "http://localhost:8006")},
    {"name": "database", "url": os.environ.get("DATABASE_CONNECTOR_URL", "http://localhost:8007")},
    {"name": "planning", "url": os.environ.get("PLANNING_URL", "http://localhost:8008")},
    {"name": "knowledge_pipelines", "url": os.environ.get("KNOWLEDGE_PIPELINES_URL", "http://localhost:8009")},
    {"name": "extensibility", "url": os.environ.get("EXTENSIBILITY_URL", "http://localhost:8010")},
]


def service_url(name: str) -> str | None:
    for s in SERVICES:
        if s["name"] == name:
            return s["url"]
    return None
