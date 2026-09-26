"""Phase 2A API tests: intelligence endpoints.

Covers the /api/intelligence, /api/test-recommendations, /api/risk-signals,
and /api/test-catalog endpoints added by the intelligence router, plus
404 behaviour for unknown components and a Phase 1 regression spot-check.

TestClient runs the FastAPI app in-process (no network).
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api.app import app

client = TestClient(app)

WARRCOPY = "copybook:WARRCOPY"
UNUSED = "copybook:UNUSED"
WARRANTY = "table:WARRANTY"
UNKNOWN = "copybook:DOES_NOT_EXIST"


def test_intelligence_bundle_has_all_keys():
    r = client.get(f"/api/intelligence/{WARRCOPY}")
    assert r.status_code == 200
    body = r.json()
    for key in ("changed_component", "impact", "recommended_tests",
                "risk_signals", "release_checklist", "ai_explanation"):
        assert key in body, f"missing key: {key}"
    assert body["changed_component"] == WARRCOPY


def test_intelligence_bundle_non_empty_sections():
    body = client.get(f"/api/intelligence/{WARRCOPY}").json()
    assert len(body["recommended_tests"]) > 0
    assert len(body["risk_signals"]) > 0
    assert len(body["release_checklist"]) > 0
    assert body["impact"]["changed_component"] == WARRCOPY


def test_intelligence_ai_explanation_valid():
    body = client.get(f"/api/intelligence/{WARRCOPY}").json()
    expl = body["ai_explanation"]
    # IntelligenceExplanation fields per ai_models.py
    assert expl.get("executive_summary"), "explanation needs a non-empty executive summary"
    assert expl.get("technical_summary") is not None


def test_unused_component_empty_recommendations_and_signals():
    body = client.get(f"/api/intelligence/{UNUSED}").json()
    assert body["recommended_tests"] == []
    assert body["risk_signals"] == []


def test_warranty_table_db2_write_signal_high():
    r = client.get(f"/api/risk-signals/{WARRANTY}")
    assert r.status_code == 200
    signals = r.json()
    matches = [s for s in signals if s["id"] == "DB2_WRITE_INVOLVED"]
    assert matches, "expected DB2_WRITE_INVOLVED signal"
    assert matches[0]["severity"] == "high"


def test_warranty_intelligence_includes_db2_signal():
    body = client.get(f"/api/intelligence/{WARRANTY}").json()
    ids = {s["id"] for s in body["risk_signals"]}
    assert "DB2_WRITE_INVOLVED" in ids


def test_test_catalog_returns_12_tests():
    r = client.get("/api/test-catalog")
    assert r.status_code == 200
    tests = r.json()
    assert len(tests) == 12
    for t in tests:
        assert "id" in t and "name" in t


def test_test_recommendations_endpoint():
    r = client.get(f"/api/test-recommendations/{WARRCOPY}")
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) > 0
    assert all("test_id" in t and "impact_level" in t for t in recs)


def test_unknown_component_404_intelligence_endpoints():
    for path in (f"/api/intelligence/{UNKNOWN}",
                 f"/api/test-recommendations/{UNKNOWN}",
                 f"/api/risk-signals/{UNKNOWN}"):
        r = client.get(path)
        assert r.status_code == 404, path


def test_phase1_impact_endpoint_still_works():
    r = client.get(f"/api/impact/{WARRCOPY}")
    assert r.status_code == 200
    body = r.json()
    assert "impacts" in body or "impacted" in body or "changed_component" in body


def test_intelligence_explanation_source_deterministic_by_default():
    # No LLM configured: the bundle must label the explanation
    # deterministic, never as AI-generated.
    body = client.get(f"/api/intelligence/{WARRCOPY}").json()
    assert body["ai_explanation"]["explanation_source"] == "deterministic"


def test_warrcopy_bundle_exposes_involved_db2_resources():
    body = client.get(f"/api/intelligence/{WARRCOPY}").json()
    impact = body["impact"]
    # WARRANTY is involved (used by impacted programs), not reverse-impacted.
    assert "table:WARRANTY" not in impact["affected_tables"]
    assert "table:WARRANTY" in impact["write_tables"]
    assert "table:WARRANTY" in impact["read_tables"]
    resources = {(r["table"], r["access"]) for r in impact["involved_resources"]}
    assert ("table:WARRANTY", "write") in resources
    assert ("table:WARRANTY", "read") in resources
    # ...and the DB2 write signal + checklist item are present.
    assert "DB2_WRITE_INVOLVED" in {s["id"] for s in body["risk_signals"]}
    assert "db2_write_involved" in {c["rule"] for c in body["release_checklist"]}


def test_unused_bundle_has_no_involved_resources():
    body = client.get(f"/api/intelligence/{UNUSED}").json()
    impact = body["impact"]
    assert impact["involved_resources"] == []
    assert impact["read_tables"] == []
    assert impact["write_tables"] == []
    assert "DB2_WRITE_INVOLVED" not in {s["id"] for s in body["risk_signals"]}
