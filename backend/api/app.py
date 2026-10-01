"""FastAPI backend for the Phase 1 Change Impact engine.

Serves the deterministically-built dependency graph:

  GET /api/components          -> all components
  GET /api/dependencies        -> all dependencies (each with evidence)
  GET /api/graph               -> {nodes, edges} for visualization
  GET /api/component/{id}      -> component + upstream/downstream edges
  GET /api/impact/{id}         -> change impact analysis for a component

The graph is built once at startup by scanning sample_mainframe/.
Component ids contain ':' (e.g. "copybook:WARRCOPY"); pass them
URL-encoded or raw - ':' is legal in a path segment.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.graph.dependency_graph import DependencyGraph
from backend.graph.impact_analyzer import ImpactAnalyzer
from backend.parsers.repository_scanner import scan_repository
from backend.api.changeset import router as changeset_router
from backend.api.github import router as github_router
from backend.api.intelligence import router as intelligence_router

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BASE_DIR / "sample_mainframe"

app = FastAPI(title="Mainframe Change Impact API",
              version="1.0.0-phase1")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 1: local dev only
    allow_methods=["GET", "POST"],  # POST added for Phase 3A change-set analysis
    allow_headers=["*"],
)


def _build() -> tuple[DependencyGraph, ImpactAnalyzer]:
    components, dependencies = scan_repository(REPO_DIR)
    graph = DependencyGraph.from_scan(components, dependencies)
    return graph, ImpactAnalyzer(graph)


GRAPH, ANALYZER = _build()
app.include_router(intelligence_router)  # Phase 2A intelligence endpoints
app.include_router(changeset_router)  # Phase 3A change-set endpoints (additive)
app.include_router(github_router)  # Phase 3B GitHub PR endpoints (additive)


# Phase 3B is a security-sensitive request boundary: with
# ``extra="forbid"`` FastAPI's default 422 body echoes caller-supplied
# values (the ``input``/``ctx`` fields), so a smuggled ``token`` or
# ``authorization`` field would be reflected back in the response. On
# the GitHub boundary we keep location, error type, and message, but
# never the supplied value. Every other endpoint keeps FastAPI's
# established validation output unchanged.
_GITHUB_VALIDATION_PREFIX = "/api/github/"


@app.exception_handler(RequestValidationError)
async def _github_boundary_validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    if request.url.path.startswith(_GITHUB_VALIDATION_PREFIX):
        sanitized = [
            {
                "loc": list(err.get("loc", ())),
                "type": err.get("type"),
                "msg": err.get("msg"),
            }
            for err in exc.errors()
        ]
        return JSONResponse(status_code=422, content={"detail": sanitized})
    return await request_validation_exception_handler(request, exc)


def _require(component_id: str) -> None:
    if not GRAPH.has(component_id):
        raise HTTPException(status_code=404,
                            detail=f"unknown component: {component_id}")


@app.get("/api/components")
def list_components() -> list[dict]:
    return GRAPH.components()


@app.get("/api/dependencies")
def list_dependencies() -> list[dict]:
    return GRAPH.dependencies()


@app.get("/api/graph")
def get_graph() -> dict:
    return {"nodes": GRAPH.components(), "edges": GRAPH.dependencies()}


@app.get("/api/component/{component_id}")
def get_component(component_id: str) -> dict:
    _require(component_id)
    return {
        "component": GRAPH.component(component_id),
        # upstream: what this component directly depends on
        "upstream": GRAPH.upstream(component_id),
        # downstream: what directly depends on this component
        "downstream": GRAPH.downstream(component_id),
    }


@app.get("/api/impact/{component_id}")
def get_impact(component_id: str) -> dict:
    _require(component_id)
    return ANALYZER.analyze(component_id)


@app.get("/api/summary")
def get_summary() -> dict:
    return GRAPH.counts()
