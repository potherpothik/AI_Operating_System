from fastapi import FastAPI

from agents.db import Base, engine, SessionLocal
from agents.reasoning_engine.api import router as reasoning_router
from agents.reasoning_engine import capability_registry
from agents.odoo_agent import register as odoo_agent_register
from agents.database_agent import register as database_agent_register
from agents.planner import register as planner_register
from agents.django_agent import register as django_agent_register
from agents.devops_agent import register as devops_agent_register
from agents.docker_agent import register as docker_agent_register
from agents.testing_agent import register as testing_agent_register
from agents.costing_agent import register as costing_agent_register
from agents.accounting_agent import register as accounting_agent_register
from agents.inventory_agent import register as inventory_agent_register
from agents.manufacturing_agent import register as manufacturing_agent_register
from agents.sales_agent import register as sales_agent_register
from agents.project_management_agent import register as project_management_agent_register
from agents.code_review_agent import register as code_review_agent_register
from agents.reverse_engineering_agent import register as reverse_engineering_agent_register
from agents.architecture_agent import register as architecture_agent_register
from agents.calculation_agent import register as calculation_agent_register
from agents.cutlist_optimization_agent import register as cutlist_optimization_agent_register
from agents.autocad_agent import register as autocad_agent_register
from agents.python_agent import register as python_agent_register
from agents.documentation_agent import register as documentation_agent_register
from agents.security_agent import register as security_agent_register
from agents.research_agent import register as research_agent_register

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="AI Orchestration Layer — Phase 5/7/8/10/14/15/16/17/18: Reasoning Engine + twenty-two agents",
    description="The shared execution loop every agent runs through, and the agents running on it.",
)

app.include_router(reasoning_router)


@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        capability_registry.load_all(db)
    finally:
        db.close()
    odoo_agent_register.ensure_template_registered()
    database_agent_register.ensure_template_registered()
    planner_register.ensure_template_registered()
    django_agent_register.ensure_template_registered()
    devops_agent_register.ensure_template_registered()
    docker_agent_register.ensure_template_registered()
    testing_agent_register.ensure_template_registered()
    costing_agent_register.ensure_template_registered()
    accounting_agent_register.ensure_template_registered()
    inventory_agent_register.ensure_template_registered()
    manufacturing_agent_register.ensure_template_registered()
    sales_agent_register.ensure_template_registered()
    project_management_agent_register.ensure_template_registered()
    code_review_agent_register.ensure_template_registered()
    reverse_engineering_agent_register.ensure_template_registered()
    architecture_agent_register.ensure_template_registered()
    calculation_agent_register.ensure_template_registered()
    cutlist_optimization_agent_register.ensure_template_registered()
    autocad_agent_register.ensure_template_registered()
    python_agent_register.ensure_template_registered()
    documentation_agent_register.ensure_template_registered()
    security_agent_register.ensure_template_registered()
    research_agent_register.ensure_template_registered()


@app.post("/capabilities/reload")
def reload_capabilities():
    db = SessionLocal()
    try:
        loaded = capability_registry.load_all(db)
    finally:
        db.close()
    return {"loaded": loaded}


@app.get("/capabilities")
def list_capabilities():
    """
    Introspection endpoint: what Reasoning Engine currently has loaded and
    actually enforces (capability_registry.load_all(), the source of
    truth for local_precheck). Phase 8's Capability Registry service
    syncs from this over HTTP rather than reaching into this service's
    own filesystem — the same inter-service-over-HTTP discipline every
    other cross-service call in this system follows.
    """
    db = SessionLocal()
    try:
        rows = db.query(capability_registry.AgentCapabilityDef).all()
        return {
            "capabilities": [
                {
                    "agent_capability": r.agent_capability,
                    "allowed_actions": r.allowed_actions,
                    "forbidden_actions": r.forbidden_actions,
                    "requires_approval": r.requires_approval,
                    "classification_ceiling": r.classification_ceiling,
                    "template_id": r.template_id,
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.post("/odoo_agent/register")
def register_odoo_agent_template():
    return odoo_agent_register.ensure_template_registered()


@app.post("/database_agent/register")
def register_database_agent_template():
    return database_agent_register.ensure_template_registered()


@app.post("/planner/register")
def register_planner_template():
    return planner_register.ensure_template_registered()


@app.post("/django_agent/register")
def register_django_agent_template():
    return django_agent_register.ensure_template_registered()


@app.post("/devops_agent/register")
def register_devops_agent_template():
    return devops_agent_register.ensure_template_registered()


@app.post("/docker_agent/register")
def register_docker_agent_template():
    return docker_agent_register.ensure_template_registered()


@app.post("/testing_agent/register")
def register_testing_agent_template():
    return testing_agent_register.ensure_template_registered()


@app.post("/costing_agent/register")
def register_costing_agent_template():
    return costing_agent_register.ensure_template_registered()


@app.post("/accounting_agent/register")
def register_accounting_agent_template():
    return accounting_agent_register.ensure_template_registered()


@app.post("/inventory_agent/register")
def register_inventory_agent_template():
    return inventory_agent_register.ensure_template_registered()


@app.post("/manufacturing_agent/register")
def register_manufacturing_agent_template():
    return manufacturing_agent_register.ensure_template_registered()


@app.post("/sales_agent/register")
def register_sales_agent_template():
    return sales_agent_register.ensure_template_registered()


@app.post("/project_management_agent/register")
def register_project_management_agent_template():
    return project_management_agent_register.ensure_template_registered()


@app.post("/code_review_agent/register")
def register_code_review_agent_template():
    return code_review_agent_register.ensure_template_registered()


@app.post("/reverse_engineering_agent/register")
def register_reverse_engineering_agent_template():
    return reverse_engineering_agent_register.ensure_template_registered()


@app.post("/architecture_agent/register")
def register_architecture_agent_template():
    return architecture_agent_register.ensure_template_registered()


@app.post("/calculation_agent/register")
def register_calculation_agent_template():
    return calculation_agent_register.ensure_template_registered()


@app.post("/cutlist_optimization_agent/register")
def register_cutlist_optimization_agent_template():
    return cutlist_optimization_agent_register.ensure_template_registered()


@app.post("/autocad_agent/register")
def register_autocad_agent_template():
    return autocad_agent_register.ensure_template_registered()


@app.post("/python_agent/register")
def register_python_agent_template():
    return python_agent_register.ensure_template_registered()


@app.post("/documentation_agent/register")
def register_documentation_agent_template():
    return documentation_agent_register.ensure_template_registered()


@app.post("/security_agent/register")
def register_security_agent_template():
    return security_agent_register.ensure_template_registered()


@app.post("/research_agent/register")
def register_research_agent_template():
    return research_agent_register.ensure_template_registered()


@app.get("/healthz")
def healthz():
    return {"status": "ok", "phase": 18}


@app.get("/")
def root():
    return {
        "status": "ok", "phase": 18,
        "modules": [
            "reasoning_engine", "odoo_agent", "database_agent", "planner",
            "django_agent", "devops_agent", "docker_agent", "testing_agent",
            "costing_agent", "accounting_agent", "inventory_agent",
            "manufacturing_agent", "sales_agent", "project_management_agent",
            "code_review_agent", "reverse_engineering_agent", "architecture_agent",
            "calculation_agent", "cutlist_optimization_agent", "autocad_agent",
            "python_agent", "documentation_agent", "security_agent", "research_agent",
        ],
    }
