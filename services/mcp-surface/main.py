from starlette.responses import JSONResponse

from mcp_surface.server import mcp

# Real MCP streamable-HTTP ASGI app, mounted at /mcp per the SDK's own
# default streamable_http_path — this is what `uvicorn main:app` serves.
app = mcp.streamable_http_app()


async def healthz(request):
    return JSONResponse({"status": "ok", "phase": 26})


app.add_route("/healthz", healthz)
