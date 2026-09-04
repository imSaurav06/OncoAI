"""
API Integration Tests using FastAPI TestClient.
"""
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.config.settings import settings

client = TestClient(app)
AUTH_HEADERS = {"X-API-Key": settings.API_KEY}


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "rdkit_version" in data


def test_readiness_check():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_auth_rejection_without_key():
    response = client.post("/v1/compounds/analyze", json={"smiles": "CCO"})
    assert response.status_code == 401


def test_analyze_compound_endpoint():
    response = client.post(
        "/v1/compounds/analyze",
        headers=AUTH_HEADERS,
        json={"smiles": "c1ccccc1O"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["descriptors"]["molecular_formula"] == "C6H6O"
    assert payload["data"]["canonical_smiles"] == "Oc1ccccc1"


def test_standardize_compound_with_salt():
    # Osimertinib mesylate
    smi = "COc1cc(N(C)CCN(C)C)c(NC(=O)C=C)cc1Nc1nccc(n1)c1cn(C)c2ccccc12.CS(=O)(=O)O"
    response = client.post(
        "/v1/compounds/standardize",
        headers=AUTH_HEADERS,
        json={"smiles": smi},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["salt_removed"] is True
    assert payload["data"]["salt_fragment_smiles"] == "CS(=O)(=O)O"


def test_compound_search_endpoint():
    response = client.post(
        "/v1/compounds/search",
        headers=AUTH_HEADERS,
        json={"min_mw": 100.0, "max_mw": 800.0, "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "items" in payload["data"]


def test_similarity_search_endpoint():
    # Search for compounds similar to Gefitinib
    gefitinib = "COc1cc2ncnc(Nc3ccc(F)c(Cl)c3)c2cc1OCCCN1CCOCC1"
    response = client.post(
        "/v1/compounds/similarity",
        headers=AUTH_HEADERS,
        json={"smiles": gefitinib, "threshold": 0.5, "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert payload["data"]["threshold"] == 0.5


def test_bioactivity_search_endpoint():
    response = client.post(
        "/v1/bioactivity/search",
        headers=AUTH_HEADERS,
        json={"gene_symbol": "EGFR", "limit": 10},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "success"
    assert "items" in payload["data"]


def test_job_submission_and_status():
    submit_res = client.post(
        "/v1/jobs",
        headers=AUTH_HEADERS,
        json={"job_type": "STANDARDIZATION", "input_params": {"batch_size": 100}},
    )
    assert submit_res.status_code == 202
    job_data = submit_res.json()["data"]
    job_id = job_data["job_id"]
    assert job_id.startswith("JOB_")

    # Poll status
    status_res = client.get(f"/v1/jobs/{job_id}", headers=AUTH_HEADERS)
    assert status_res.status_code == 200
    assert status_res.json()["data"]["job_id"] == job_id


def test_multi_tenant_job_isolation():
    """Verify that Tenant B cannot access or view Tenant A's private background jobs."""
    tenant_a_headers = {"X-API-Key": "onco_sk_tenant_pharma_a_sec123"}
    tenant_b_headers = {"X-API-Key": "onco_sk_tenant_biotech_b_sec456"}

    # Tenant A submits a job
    res = client.post(
        "/v1/jobs",
        headers=tenant_a_headers,
        json={"job_type": "STANDARDIZATION", "input_params": {"target": "BRAF"}},
    )
    assert res.status_code == 202
    job_id = res.json()["data"]["job_id"]

    # Tenant A can access their own job
    res_a = client.get(f"/v1/jobs/{job_id}", headers=tenant_a_headers)
    assert res_a.status_code == 200
    assert res_a.json()["data"]["job_id"] == job_id

    # Tenant B is blocked from viewing Tenant A's job (404 Not Found)
    res_b = client.get(f"/v1/jobs/{job_id}", headers=tenant_b_headers)
    assert res_b.status_code == 404


def test_analyze_stereochemistry_flag():
    """Verify that /v1/compounds/analyze accurately flags presence of stereocenters."""
    # L-alanine has defined stereocenter
    res_chiral = client.post(
        "/v1/compounds/analyze",
        headers=AUTH_HEADERS,
        json={"smiles": "C[C@@H](N)C(=O)O"},
    )
    assert res_chiral.status_code == 200
    assert res_chiral.json()["data"]["has_stereochemistry"] is True
    assert "@" in res_chiral.json()["data"]["canonical_smiles"]

    # Ethanol is achiral
    res_achiral = client.post(
        "/v1/compounds/analyze",
        headers=AUTH_HEADERS,
        json={"smiles": "CCO"},
    )
    assert res_achiral.status_code == 200
    assert res_achiral.json()["data"]["has_stereochemistry"] is False


def test_bioactivity_search_censored_filter():
    """Verify that /v1/bioactivity/search can filter censored observations and exposes p_activity_relation."""
    res = client.post(
        "/v1/bioactivity/search",
        headers=AUTH_HEADERS,
        json={"is_censored": True, "limit": 10},
    )
    assert res.status_code == 200
    items = res.json()["data"]["items"]
    for item in items:
        assert item["is_censored"] is True
        assert item["p_activity_relation"] in ("<", "<=", ">", ">=", "~")
