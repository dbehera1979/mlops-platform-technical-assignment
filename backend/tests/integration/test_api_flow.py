"""End-to-end acceptance-scenario tests driven through the HTTP API,
exercising auth, RBAC, and the full request/response contract — not
just the service layer (see tests/unit for that).

Deployment execution is async (Phase 3): a POST that triggers real work
returns 202 with the deployment still REQUESTED, and the test awaits
`deployment_worker.wait_for_deployment` before asserting the final state
— exactly what a real client would do by polling GET instead."""
import pytest

from app.services import deployment_worker
from tests.conftest import auth_headers


@pytest.mark.asyncio
async def test_health_endpoint(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_full_registry_to_production_flow(client):
    operator_headers = await auth_headers(client, "operator")
    approver_headers = await auth_headers(client, "approver")

    # 1. Register a model and two versions.
    resp = await client.post(
        "/models", json={"name": "fraud-detector", "owner_team": "risk-ml"},
        headers=operator_headers,
    )
    assert resp.status_code == 201
    model_id = resp.json()["id"]

    v1 = await client.post(
        f"/models/{model_id}/versions",
        json={
            "version_label": "v1", "framework": "sklearn", "algorithm": "xgboost",
            "artifact_uri": "s3://bucket/v1",
        },
        headers=operator_headers,
    )
    v2 = await client.post(
        f"/models/{model_id}/versions",
        json={
            "version_label": "v2", "framework": "sklearn", "algorithm": "xgboost",
            "artifact_uri": "s3://bucket/v2",
        },
        headers=operator_headers,
    )
    assert v1.status_code == 201 and v2.status_code == 201
    v1_id, v1_row_version = v1.json()["id"], v1.json()["row_version"]

    # 2. Approve one version (VALIDATED -> APPROVED).
    resp = await client.post(
        f"/models/versions/{v1_id}/promote",
        json={
            "to_stage": "VALIDATED", "approved_by": "approver",
            "expected_row_version": v1_row_version,
        },
        headers=approver_headers,
    )
    assert resp.status_code == 200
    row_version = resp.json()["row_version"]
    resp = await client.post(
        f"/models/versions/{v1_id}/promote",
        json={
            "to_stage": "APPROVED", "approved_by": "approver",
            "expected_row_version": row_version,
        },
        headers=approver_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["lifecycle_stage"] == "APPROVED"

    # 3. Prevent the OTHER (unapproved) version from PRODUCTION deployment.
    v2_id = v2.json()["id"]
    resp = await client.post(
        "/deployments",
        json={
            "model_version_id": v2_id, "environment": "PRODUCTION",
            "idempotency_key": "attempt-unapproved",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "VALIDATION_FAILED"

    # 4. Deploy the approved version. 202 = accepted, executing async.
    resp = await client.post(
        "/deployments",
        json={
            "model_version_id": v1_id, "environment": "PRODUCTION",
            "idempotency_key": "deploy-v1", "simulate_failure": False,
        },
        headers=operator_headers,
    )
    assert resp.status_code == 202
    deployment = resp.json()
    assert deployment["status"] == "REQUESTED"

    await deployment_worker.wait_for_deployment(deployment["id"])
    resp = await client.get(f"/deployments/{deployment['id']}", headers=operator_headers)
    assert resp.json()["status"] == "SUCCEEDED"

    # 5. Monitoring data appears after a successful PRODUCTION deployment
    #    (the worker seeds an initial snapshot on go-live).
    resp = await client.get(f"/models/{model_id}/metrics", headers=operator_headers)
    assert resp.status_code == 200
    assert len(resp.json()["snapshots"]) >= 1

    # 8. Duplicate deployment request is handled safely (same key -> 200,
    #    same deployment id, not a new one).
    resp = await client.post(
        "/deployments",
        json={
            "model_version_id": v1_id, "environment": "PRODUCTION",
            "idempotency_key": "deploy-v1",
        },
        headers=operator_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == deployment["id"]

    # 7. Roll back a PRODUCTION deployment — needs a second SUCCEEDED
    #    deployment first (nothing prior to roll back to otherwise).
    resp = await client.post(
        "/deployments",
        json={
            "model_version_id": v1_id, "environment": "PRODUCTION",
            "idempotency_key": "deploy-v1-again", "simulate_failure": False,
        },
        headers=operator_headers,
    )
    second_deployment_id = resp.json()["id"]
    await deployment_worker.wait_for_deployment(second_deployment_id)

    resp = await client.post(
        f"/deployments/{second_deployment_id}/rollback", headers=operator_headers
    )
    assert resp.status_code == 202
    rollback_id = resp.json()["id"]
    await deployment_worker.wait_for_deployment(rollback_id)

    resp = await client.get(f"/deployments/{rollback_id}", headers=operator_headers)
    assert resp.json()["status"] == "ROLLED_BACK"


@pytest.mark.asyncio
async def test_deployment_failure_and_retry_flow(client):
    """6. Retry a failed deployment — driven through the HTTP API with a
    forced failure, then a forced-success retry."""
    operator_headers = await auth_headers(client, "operator")
    approver_headers = await auth_headers(client, "approver")

    resp = await client.post(
        "/models", json={"name": "churn-model"}, headers=operator_headers
    )
    model_id = resp.json()["id"]
    resp = await client.post(
        f"/models/{model_id}/versions",
        json={
            "version_label": "v1", "framework": "pytorch", "algorithm": "lstm",
            "artifact_uri": "s3://bucket/churn/v1",
        },
        headers=operator_headers,
    )
    version_id, row_version = resp.json()["id"], resp.json()["row_version"]

    for to_stage in ("VALIDATED", "APPROVED"):
        resp = await client.post(
            f"/models/versions/{version_id}/promote",
            json={"to_stage": to_stage, "approved_by": "approver", "expected_row_version": row_version},
            headers=approver_headers,
        )
        row_version = resp.json()["row_version"]

    resp = await client.post(
        "/deployments",
        json={
            "model_version_id": version_id, "environment": "STAGING",
            "idempotency_key": "churn-deploy-1", "simulate_failure": True,
        },
        headers=operator_headers,
    )
    deployment_id = resp.json()["id"]
    await deployment_worker.wait_for_deployment(deployment_id)

    resp = await client.get(f"/deployments/{deployment_id}", headers=operator_headers)
    assert resp.json()["status"] == "FAILED"
    assert resp.json()["failure_class"] in ("TRANSIENT", "TERMINAL")

    resp = await client.post(
        f"/deployments/{deployment_id}/retry?simulate_failure=false",
        headers=operator_headers,
    )
    assert resp.status_code == 202
    retry_id = resp.json()["id"]
    await deployment_worker.wait_for_deployment(retry_id)

    resp = await client.get(f"/deployments/{retry_id}", headers=operator_headers)
    assert resp.json()["status"] == "SUCCEEDED"
    assert resp.json()["previous_deployment_id"] == deployment_id


@pytest.mark.asyncio
async def test_viewer_role_cannot_create_model(client):
    viewer_headers = await auth_headers(client, "viewer")
    resp = await client.post(
        "/models", json={"name": "should-fail"}, headers=viewer_headers
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(client):
    resp = await client.post("/models", json={"name": "no-auth"})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_unauthenticated_read_rejected(client):
    """Reads require SOME authenticated role (any of the four), even
    though no specific role is required — this was a real gap caught
    during the Phase 6 review: GET routes had no auth dependency at all
    until this was fixed alongside this test."""
    resp = await client.get("/models")
    assert resp.status_code == 401
    resp = await client.get("/deployments")
    assert resp.status_code == 401
