"""Test-catalog validation tests.

Business behavior, not implementation trivia. The catalog loader must hold
the same validation standard as the historical incident dataset:

- the file is valid YAML with a ``tests`` list
- every test id is unique and non-empty
- every ``covers[]`` entry is a real Phase 1 component id
- ``execution.job`` (when present) names a real JCL job component
- invalid data fails clearly at load time (TestCatalogError), never
  silently dropped — and raw parser exceptions never leak through

The validation must not change test-selection semantics: recommendations
computed from a validated catalog are identical to the unvalidated one.
"""
from __future__ import annotations

import pytest
import yaml
from fastapi import HTTPException

import backend.api.intelligence as intel_api
from backend.intelligence.impact_context import _shared, build_impact_context
from backend.intelligence.test_catalog import (
    TestCatalogError,
    load_catalog,
)
from backend.intelligence.test_selector import recommend_tests


@pytest.fixture(scope="module")
def graph_components():
    graph, _ = _shared()
    return {c["id"]: c for c in graph.components()}


@pytest.fixture(scope="module")
def valid_ids(graph_components):
    return set(graph_components)


@pytest.fixture(scope="module")
def valid_jobs(graph_components):
    return {
        cid for cid, comp in graph_components.items()
        if comp["type"] == "JCL_JOB"
    }


def _entry(test_id="TC-9001", covers=("program:WARR001",),
           job="WARRBTCH", **overrides):
    entry = {
        "id": test_id,
        "name": f"Test {test_id}",
        "type": "regression",
        "covers": list(covers),
        "description": "synthetic",
    }
    if job is not None:
        entry["execution"] = {"job": job}
    entry.update(overrides)
    return entry


def _write_catalog(tmp_path, tests):
    path = tmp_path / "test_catalog.yaml"
    path.write_text(yaml.safe_dump({"tests": tests}))
    return path


# ------------------------------------------------------------------
# Positive: the real catalog validates against the real graph
# ------------------------------------------------------------------

def test_real_catalog_validates_against_graph(valid_ids, valid_jobs):
    catalog = load_catalog(
        valid_component_ids=valid_ids, valid_job_ids=valid_jobs
    )
    assert len(catalog) == 12
    assert len({t.id for t in catalog}) == 12


def test_validation_does_not_change_test_selection(valid_ids, valid_jobs):
    # The validated catalog must produce identical recommendations to the
    # unvalidated load: validation changes nothing about selection.
    ctx = build_impact_context("copybook:WARRCOPY")
    plain = recommend_tests(ctx, load_catalog())
    validated = recommend_tests(
        ctx,
        load_catalog(
            valid_component_ids=valid_ids, valid_job_ids=valid_jobs
        ),
    )
    assert [r.test_id for r in validated] == [r.test_id for r in plain]
    assert [r.impact_level for r in validated] == [
        r.impact_level for r in plain]


def test_bare_job_name_accepted(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(tmp_path, [_entry(job="WARRBTCH")])
    catalog = load_catalog(
        path=path, valid_component_ids=valid_ids, valid_job_ids=valid_jobs
    )
    assert catalog[0].execution == {"job": "WARRBTCH"}


def test_full_job_component_id_accepted(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(tmp_path, [_entry(job="job:WARRBTCH")])
    catalog = load_catalog(
        path=path, valid_component_ids=valid_ids, valid_job_ids=valid_jobs
    )
    assert catalog[0].id == "TC-9001"


def test_missing_execution_is_allowed(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(tmp_path, [_entry(job=None)])
    catalog = load_catalog(
        path=path, valid_component_ids=valid_ids, valid_job_ids=valid_jobs
    )
    assert catalog[0].execution is None


# ------------------------------------------------------------------
# Negative: invalid data fails clearly at load time
# ------------------------------------------------------------------

def test_duplicate_test_ids_rejected(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(
        tmp_path, [_entry("TC-9001"), _entry("TC-9001")]
    )
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert "duplicate test id" in str(exc_info.value)
    assert "TC-9001" in str(exc_info.value)


def test_unknown_covers_component_rejected(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(
        tmp_path, [_entry(covers=("program:FAKE999",))]
    )
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert "program:FAKE999" in str(exc_info.value)
    assert "TC-9001" in str(exc_info.value)


def test_execution_job_must_exist(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(tmp_path, [_entry(job="NOPEJOB")])
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert "NOPEJOB" in str(exc_info.value)


def test_execution_job_must_be_a_jcl_job(valid_ids, valid_jobs, tmp_path):
    # program:WARR001 exists in the graph but is not a JCL job.
    path = _write_catalog(tmp_path, [_entry(job="program:WARR001")])
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert "not a JCL job" in str(exc_info.value)


def test_empty_covers_rejected(valid_ids, valid_jobs, tmp_path):
    path = _write_catalog(tmp_path, [_entry(covers=[])])
    with pytest.raises(TestCatalogError):
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )


def test_malformed_yaml_raises_curated_error(valid_ids, valid_jobs,
                                             tmp_path):
    # A corrupt catalog must produce the curated TestCatalogError,
    # never leak a raw yaml.parser.ParserError.
    path = tmp_path / "test_catalog.yaml"
    path.write_text("tests: [unclosed\n")
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert not isinstance(exc_info.value, yaml.YAMLError)
    assert "not valid YAML" in str(exc_info.value)


def test_missing_tests_key_rejected(valid_ids, valid_jobs, tmp_path):
    path = tmp_path / "test_catalog.yaml"
    path.write_text(yaml.safe_dump({"not_tests": []}))
    with pytest.raises(TestCatalogError) as exc_info:
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )
    assert "'tests' list" in str(exc_info.value)


def test_non_mapping_entry_rejected(valid_ids, valid_jobs, tmp_path):
    path = tmp_path / "test_catalog.yaml"
    path.write_text(yaml.safe_dump({"tests": ["nope"]}))
    with pytest.raises(TestCatalogError):
        load_catalog(
            path=path, valid_component_ids=valid_ids,
            valid_job_ids=valid_jobs,
        )


# ------------------------------------------------------------------
# API contract: catalog errors fail clearly, never leak parser details
# ------------------------------------------------------------------

def test_api_converts_catalog_error_to_500(monkeypatch):
    def boom(**kwargs):
        raise TestCatalogError("catalog broken for test")

    monkeypatch.setattr(intel_api, "load_catalog", boom)
    with pytest.raises(HTTPException) as exc_info:
        intel_api.get_test_catalog()
    assert exc_info.value.status_code == 500
    assert "catalog broken for test" in str(exc_info.value.detail)
