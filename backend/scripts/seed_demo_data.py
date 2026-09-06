#!/usr/bin/env python3
"""Seeds a running instance of the MLOps Platform with realistic demo
data — several models, multiple versions each at different lifecycle
stages, a mix of successful/failed/retried/rolled-back deployments, and
(via the deployment worker's automatic seeding) monitoring snapshots for
anything that reaches PRODUCTION.

Run against a server that's already up:

    python scripts/seed_demo_data.py
    python scripts/seed_demo_data.py --base-url http://localhost:8000

Safe to re-run: model names are unique, so a second run skips models that
already exist (logged, not treated as an error) rather than failing or
duplicating data.

Reads its data from scripts/seed_data.json — edit that file to change
what gets seeded without touching this script.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

DATA_FILE = Path(__file__).parent / "seed_data.json"
POLL_INTERVAL_S = 0.3
POLL_MAX_ATTEMPTS = 30
TERMINAL_STATUSES = {"SUCCEEDED", "FAILED", "ROLLED_BACK"}

# Direct promotions only ever move one step; to reach APPROVED/PRODUCTION
# from DRAFT you walk the chain. PRODUCTION is reached via a deployment,
# never a direct promotion (architecture.md §6.1) — handled separately.
PROMOTION_CHAIN = ["DRAFT", "VALIDATED", "APPROVED", "STAGING"]


class SeedError(RuntimeError):
    pass


def login(client: httpx.Client, username: str) -> str:
    resp = client.post("/auth/token", data={"username": username, "password": "seed"})
    resp.raise_for_status()
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def get_or_create_model(client: httpx.Client, op_headers: dict, model_def: dict) -> str:
    resp = client.get("/models", params={"search": model_def["name"]}, headers=op_headers)
    resp.raise_for_status()
    for m in resp.json():
        if m["name"] == model_def["name"]:
            print(f"  model '{model_def['name']}' already exists, reusing")
            return m["id"]

    resp = client.post(
        "/models",
        json={
            "name": model_def["name"],
            "description": model_def.get("description"),
            "owner_team": model_def.get("owner_team"),
        },
        headers=op_headers,
    )
    resp.raise_for_status()
    model = resp.json()
    print(f"  created model '{model['name']}' ({model['id']})")
    return model["id"]


def get_or_create_version(client: httpx.Client, op_headers: dict, model_id: str, version_def: dict) -> dict:
    resp = client.get(f"/models/{model_id}/versions", headers=op_headers)
    resp.raise_for_status()
    for v in resp.json():
        if v["version_label"] == version_def["version_label"]:
            print(f"    version '{v['version_label']}' already exists, reusing ({v['lifecycle_stage']})")
            return v

    resp = client.post(
        f"/models/{model_id}/versions",
        json={
            "version_label": version_def["version_label"],
            "framework": version_def["framework"],
            "algorithm": version_def["algorithm"],
            "artifact_uri": version_def["artifact_uri"],
            "training_data_ref": version_def.get("training_data_ref"),
            "tags": version_def.get("tags", {}),
            "created_by": version_def.get("created_by", "seed-script"),
        },
        headers=op_headers,
    )
    resp.raise_for_status()
    version = resp.json()
    print(f"    registered version '{version['version_label']}' ({version['lifecycle_stage']})")
    return version


def promote_to(client: httpx.Client, ap_headers: dict, version: dict, target_stage: str) -> dict:
    """Walks PROMOTION_CHAIN from the version's current stage up to (and
    including) target_stage, one promotion call per step. A no-op if the
    version is already at/past the target (idempotent re-runs) — this
    includes PRODUCTION/ARCHIVED, which sit outside PROMOTION_CHAIN
    entirely and are never something to promote *away* from here."""
    if target_stage not in PROMOTION_CHAIN:
        return version  # PRODUCTION / DRAFT (no-op) handled by caller
    if version["lifecycle_stage"] not in PROMOTION_CHAIN:
        # PRODUCTION or ARCHIVED — already beyond anything PROMOTION_CHAIN
        # covers; nothing to do.
        return version
    current_index = PROMOTION_CHAIN.index(version["lifecycle_stage"])
    target_index = PROMOTION_CHAIN.index(target_stage)

    for stage in PROMOTION_CHAIN[current_index + 1 : target_index + 1]:
        resp = client.post(
            f"/models/versions/{version['id']}/promote",
            json={
                "to_stage": stage,
                "approved_by": "seed-script",
                "decision": "APPROVED",
                "expected_row_version": version["row_version"],
            },
            headers=ap_headers,
        )
        resp.raise_for_status()
        version = resp.json()
        print(f"    promoted '{version['version_label']}' -> {version['lifecycle_stage']}")
    return version


def poll_until_terminal(client: httpx.Client, headers: dict, deployment_id: str) -> dict:
    for _ in range(POLL_MAX_ATTEMPTS):
        resp = client.get(f"/deployments/{deployment_id}", headers=headers)
        resp.raise_for_status()
        deployment = resp.json()
        if deployment["status"] in TERMINAL_STATUSES:
            return deployment
        time.sleep(POLL_INTERVAL_S)
    raise SeedError(f"Deployment {deployment_id} did not reach a terminal status in time")


def run_deploy_step(client: httpx.Client, op_headers: dict, version: dict, step: dict, seq: str) -> None:
    environment = step["environment"]
    outcome = step["outcome"]
    idempotency_key = f"seed:{version['id']}:{environment}:{seq}"

    simulate_failure = outcome in ("fail_then_retry_succeed",)
    resp = client.post(
        "/deployments",
        json={
            "model_version_id": version["id"],
            "environment": environment,
            "idempotency_key": idempotency_key,
            "requested_by": "seed-script",
            "simulate_failure": simulate_failure,
        },
        headers=op_headers,
    )
    if resp.status_code == 409:
        print(f"    deploy to {environment} skipped: {resp.json()['error']['message']}")
        return
    resp.raise_for_status()
    deployment = poll_until_terminal(client, op_headers, resp.json()["id"])
    print(f"    deployed '{version['version_label']}' to {environment}: {deployment['status']}")

    if outcome == "fail_then_retry_succeed" and deployment["status"] == "FAILED":
        resp = client.post(
            f"/deployments/{deployment['id']}/retry",
            params={"simulate_failure": "false"},
            headers=op_headers,
        )
        resp.raise_for_status()
        retried = poll_until_terminal(client, op_headers, resp.json()["id"])
        print(f"    retried -> {retried['status']}")

    if outcome == "succeed_then_rollback" and deployment["status"] == "SUCCEEDED":
        resp = client.post(f"/deployments/{deployment['id']}/rollback", headers=op_headers)
        if resp.status_code == 422:
            print(f"    rollback skipped: {resp.json()['error']['message']}")
            return
        resp.raise_for_status()
        rolled_back = poll_until_terminal(client, op_headers, resp.json()["id"])
        print(f"    rolled back -> {rolled_back['status']}")


def seed(base_url: str) -> None:
    data = json.loads(DATA_FILE.read_text())

    with httpx.Client(base_url=base_url, timeout=30) as client:
        try:
            op_token = login(client, "operator")
            ap_token = login(client, "approver")
        except httpx.HTTPError as exc:
            raise SeedError(f"Could not authenticate against {base_url} — is the API running? ({exc})") from exc

        op_headers = auth_headers(op_token)
        ap_headers = auth_headers(ap_token)

        for model_def in data["models"]:
            print(f"\n{model_def['name']}")
            model_id = get_or_create_model(client, op_headers, model_def)

            for seq, version_def in enumerate(model_def["versions"], start=1):
                version = get_or_create_version(client, op_headers, model_id, version_def)

                target = version_def.get("promote_to", "DRAFT")
                if target != "DRAFT":
                    version = promote_to(client, ap_headers, version, target if target != "PRODUCTION" else "APPROVED")

                for step_index, step in enumerate(version_def.get("deploy", []), start=1):
                    run_deploy_step(client, op_headers, version, step, f"{seq}-{step_index}")

    print("\nSeed complete.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base-url", default="http://localhost:8000", help="API base URL (default: %(default)s)")
    args = parser.parse_args()

    try:
        seed(args.base_url)
    except SeedError as exc:
        print(f"\nSeed failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
