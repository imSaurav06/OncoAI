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
