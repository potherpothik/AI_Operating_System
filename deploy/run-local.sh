#!/usr/bin/env bash
# Start AIOS local stack (minimal UI path) using repo .venv.
# Logs: deploy/logs/<service>.log  PIDs: deploy/logs/pids.txt
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VENV="$REPO/.venv"
LOGDIR="$REPO/deploy/logs"
PIDFILE="$LOGDIR/pids.txt"
UVICORN="$VENV/bin/uvicorn"
MODEL="${AIOS_LOCAL_MODEL:-qwen3.5:4b}"

mkdir -p /tmp/ai_os_sandbox /tmp/ai_os_plugins "$LOGDIR"

if [[ ! -x "$UVICORN" ]]; then
  echo "Missing $UVICORN"
  echo "Create venv:  python3.12 -m venv .venv && pip install -r services/governance/requirements.txt ..."
  echo "See docs/installation-guide.md"
  exit 1
fi

stop_all() {
  if [[ -f "$PIDFILE" ]]; then
    while read -r pid name; do
      kill "$pid" 2>/dev/null || true
    done < "$PIDFILE"
    rm -f "$PIDFILE"
  fi
}

start_one() {
  local name="$1" port="$2" dir="$3"
  shift 3
  cd "$REPO/services/$dir"
  nohup env "$@" "$UVICORN" main:app --host 127.0.0.1 --port "$port" \
    >"$LOGDIR/${name}.log" 2>&1 &
  echo "$! $name" >> "$PIDFILE"
  echo "started $name on :$port (pid $!)"
}

case "${1:-start}" in
  stop)
    stop_all
    echo "stopped"
    exit 0
    ;;
  start)
    stop_all
    : > "$PIDFILE"
    ;;
  *)
    echo "Usage: $0 [start|stop]"
    exit 1
    ;;
esac

start_one governance 8000 governance SECURITY_LAYER_URL=http://localhost:8000
sleep 1
start_one platform-spine 8002 platform-spine SECURITY_LAYER_URL=http://localhost:8000
start_one knowledge 8003 knowledge SECURITY_LAYER_URL=http://localhost:8000
start_one assembly 8004 assembly \
  SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 KNOWLEDGE_URL=http://localhost:8003
start_one execution 8006 execution \
  SECURITY_LAYER_URL=http://localhost:8000 SANDBOX_ROOT=/tmp/ai_os_sandbox CODE_ANALYSIS_URL=http://localhost:8009
start_one database 8007 database SECURITY_LAYER_URL=http://localhost:8000
start_one agents 8005 agents \
  SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
  KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
  EXECUTION_URL=http://localhost:8006 PROPOSAL_REPO_PATH=/tmp/ai_os_sandbox \
  DATABASE_CONNECTOR_URL=http://localhost:8007 CAPABILITY_REGISTRY_URL=http://localhost:8008 \
  KNOWLEDGE_PIPELINES_URL=http://localhost:8009 PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins
start_one planning 8008 planning \
  SECURITY_LAYER_URL=http://localhost:8000 AGENTS_URL=http://localhost:8005 PLATFORM_URL=http://localhost:8002
start_one knowledge_pipelines 8009 knowledge_pipelines \
  SECURITY_LAYER_URL=http://localhost:8000 KNOWLEDGE_URL=http://localhost:8003 \
  DATABASE_CONNECTOR_URL=http://localhost:8007 ASSEMBLY_URL=http://localhost:8004
start_one extensibility 8010 extensibility \
  SECURITY_LAYER_URL=http://localhost:8000 ASSEMBLY_URL=http://localhost:8004 \
  AGENTS_URL=http://localhost:8005 PLUGIN_CAPABILITIES_DIR=/tmp/ai_os_plugins
start_one observability 8013 observability \
  GOVERNANCE_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
  KNOWLEDGE_URL=http://localhost:8003 ASSEMBLY_URL=http://localhost:8004 \
  AGENTS_URL=http://localhost:8005 EXECUTION_URL=http://localhost:8006 \
  DATABASE_CONNECTOR_URL=http://localhost:8007 PLANNING_URL=http://localhost:8008 \
  KNOWLEDGE_PIPELINES_URL=http://localhost:8009 EXTENSIBILITY_URL=http://localhost:8010
start_one control-ui 8024 control-ui \
  SECURITY_LAYER_URL=http://localhost:8000 PLATFORM_URL=http://localhost:8002 \
  OBSERVABILITY_URL=http://localhost:8013

echo "waiting for core services..."
for i in $(seq 1 30); do
  if curl -sf http://localhost:8000/security/policy/human_admin >/dev/null \
     && curl -sf http://localhost:8002/config/gateway >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -sf -X POST http://localhost:8002/config/override \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d "{\"service\":\"reasoning_engine\",\"key\":\"default_local_model\",\"value\":\"$MODEL\",\"set_by\":\"human_admin\"}" >/dev/null || true
curl -sf -X POST http://localhost:8002/config/override \
  -H "Authorization: Bearer dev-admin-token" \
  -H "Content-Type: application/json" \
  -d "{\"service\":\"reasoning_engine\",\"key\":\"fallback_local_model\",\"value\":\"$MODEL\",\"set_by\":\"human_admin\"}" >/dev/null || true

curl -sf -X POST http://localhost:8008/capabilities/sync \
  -H "Authorization: Bearer dev-admin-token" >/dev/null || true

echo ""
echo "Backend ready. Start Web UI:  cd web && npm run dev"
echo "Open http://localhost:3000  token: dev-admin-token"
echo "Model override: $MODEL"
echo "Stop: $0 stop"
