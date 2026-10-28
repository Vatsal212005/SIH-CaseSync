from datetime import date, timedelta

from app.core.database import SessionLocal
from app.models import ComplaintEmbedding
from app.tests.conftest import login


def _run_scenario(client, headers, scenario: str):
    response = client.post("/api/v1/demo/sessions", headers=headers, json={"scenario": scenario})
    assert response.status_code == 200, response.text
    session = response.json()
    while session["status"] == "active":
        if scenario == "duplicate_investigations" and session["current_step"] == 4:
            finding = session["finding"]
            response = client.post(
                f"/api/v1/overlaps/{finding['id']}/review",
                headers=headers,
                json={
                    "decision": "confirmed",
                    "notes": "Explicit human review for the interactive demonstration test.",
                    "create_coordination": False,
                },
            )
            assert response.status_code == 200, response.text
        if scenario == "duplicate_investigations" and session["current_step"] == 5:
            me = client.get("/api/v1/auth/me").json()
            bureau_ids = list({row["bureau"]["id"] for row in session["complaints"]})
            response = client.post(
                f"/api/v1/overlaps/{session['finding']['id']}/coordinate",
                headers=headers,
                json={
                    "owner_id": me["id"],
                    "bureau_ids": bureau_ids,
                    "officer_ids": [],
                    "next_action": "Jointly verify the synthetic fee evidence",
                    "assignee_id": me["id"],
                    "due_date": str(date.today() + timedelta(days=7)),
                    "remarks": "Explicit coordination after the recorded human decision.",
                    "request_key": f"test:demo:{session['id']}:coordination",
                },
            )
            assert response.status_code == 200, response.text
        response = client.post(
            f"/api/v1/demo/sessions/{session['id']}/advance",
            headers=headers,
            json={"expected_step": session["current_step"]},
        )
        assert response.status_code == 200, response.text
        session = response.json()
    return session


def test_demo_scenarios_use_computed_services_and_isolated_sessions(client, central):
    session = _run_scenario(client, central, "duplicate_investigations")

    assert session["status"] == "completed"
    assert len(session["complaints"]) == 2
    assert session["finding"] is not None
    assert 0 <= session["finding"]["semantic_score"] <= 1
    assert session["result"]["events"][3]["title"] == "MiniLM overlap evaluation completed"
    assert session["analysis"]["embedding_dimensions"] == 384
    assert session["analysis"]["components"]["semantic"] >= 0
    assert session["finding"]["review_state"] == "confirmed"
    assert session["coordination"] is not None

    complaint = client.get(f"/api/v1/complaints/{session['complaints'][0]['id']}").json()
    event_types = [event["type"] for event in complaint["journey"]]
    assert event_types == [
        event["type"]
        for event in sorted(complaint["journey"], key=lambda row: row["timestamp"])
    ]
    assert "registered" in event_types
    assert "coordination_started" in event_types

    records = client.get("/api/v1/coordination").json()
    record = next(row for row in records if row["id"] == session["coordination"]["id"])
    assert set(record["complaint_ids"]) == {row["id"] for row in session["complaints"]}
    assert len(record["participants"]) == len(record["participant_details"])
    assert record["action_items"] and record["action_items"][0]["completed"] is False

    finding = client.get(f"/api/v1/overlaps/{session['finding']['id']}").json()
    payload = {
        "owner_id": client.get("/api/v1/auth/me").json()["id"],
        "bureau_ids": [finding["complaint_a"]["assigned_bureau"]["id"], finding["complaint_b"]["assigned_bureau"]["id"]],
        "officer_ids": [],
        "next_action": "Verify the shared synthetic evidence",
        "assignee_id": client.get("/api/v1/auth/me").json()["id"],
        "due_date": str(date.today() + timedelta(days=7)),
        "remarks": "Idempotency verification for the synthetic coordination workflow.",
        "request_key": "test:coordination:retry",
    }
    first = client.post(f"/api/v1/overlaps/{session['finding']['id']}/coordinate", headers=central, json=payload)
    second = client.post(f"/api/v1/overlaps/{session['finding']['id']}/coordinate", headers=central, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"] == session["coordination"]["id"]
    assert first.json()["created"] is False and second.json()["created"] is False


def test_demo_restart_archives_only_its_session(client, central):
    before = client.get("/api/v1/complaints?page_size=1").json()["total"]
    started = client.post("/api/v1/demo/sessions", headers=central, json={"scenario": "different_complaints"}).json()
    advanced = client.post(
        f"/api/v1/demo/sessions/{started['id']}/advance",
        headers=central,
        json={"expected_step": 0},
    ).json()
    replacement = client.post(f"/api/v1/demo/sessions/{started['id']}/restart", headers=central).json()

    assert replacement["id"] != started["id"]
    assert replacement["current_step"] == 0 and replacement["status"] == "active"
    assert client.get(f"/api/v1/demo/sessions/{started['id']}").json()["status"] == "archived"
    assert client.get("/api/v1/complaints?page_size=1").json()["total"] == before
    assert advanced["institution_id"] is not None


def test_demo_recovery_and_explicit_review_boundary(client, central):
    started = client.post(
        "/api/v1/demo/sessions", headers=central, json={"scenario": "duplicate_investigations"}
    ).json()
    session = started
    for _ in range(4):
        response = client.post(
            f"/api/v1/demo/sessions/{session['id']}/advance",
            headers=central,
            json={"expected_step": session["current_step"]},
        )
        assert response.status_code == 200, response.text
        session = response.json()

    assert session["current_step"] == 4
    assert session["finding"]["review_state"] == "pending"
    assert session["analysis"]["model"]
    assert session["complaints"][0]["description"]
    blocked = client.post(
        f"/api/v1/demo/sessions/{session['id']}/advance",
        headers=central,
        json={"expected_step": 4},
    )
    assert blocked.status_code == 409

    recovery = client.get("/api/v1/demo/sessions/current").json()
    assert recovery["current"]["id"] == session["id"]
    assert recovery["current"]["current_step"] == 4


def test_demo_defers_embedding_until_the_explicit_analysis_step(client, central):
    session = client.post(
        "/api/v1/demo/sessions", headers=central, json={"scenario": "duplicate_investigations"}
    ).json()
    for _ in range(3):
        response = client.post(
            f"/api/v1/demo/sessions/{session['id']}/advance",
            headers=central,
            json={"expected_step": session["current_step"]},
        )
        assert response.status_code == 200, response.text
        session = response.json()

    complaint_ids = [row["id"] for row in session["complaints"]]
    with SessionLocal() as db:
        assert db.query(ComplaintEmbedding).filter(ComplaintEmbedding.complaint_id.in_(complaint_ids)).count() == 0

    response = client.post(
        f"/api/v1/demo/sessions/{session['id']}/advance",
        headers=central,
        json={"expected_step": session["current_step"]},
    )
    assert response.status_code == 200, response.text
    analyzed = response.json()
    assert analyzed["analysis"]["embedding_dimensions"] == 384
    with SessionLocal() as db:
        assert db.query(ComplaintEmbedding).filter(ComplaintEmbedding.complaint_id.in_(complaint_ids)).count() == 2


def test_institution_intelligence_action_center_and_permissions(client, central):
    session = _run_scenario(client, central, "different_complaints")
    intelligence = client.get(f"/api/v1/institutions/{session['institution_id']}").json()

    assert intelligence["is_synthetic"] is True
    assert intelligence["total_complaints"] == len(intelligence["complaints"]) == 2
    assert sum(row["value"] for row in intelligence["analytics"]["categories"]) == 2
    assert sum(row["value"] for row in intelligence["analytics"]["bureaus"]) == 2
    assert intelligence["insights"]

    center = client.get("/api/v1/dashboard/actions").json()
    ranks = [item["rank"] for item in center["items"]]
    assert ranks == sorted(ranks)
    assert center["rules"][0] == "Overdue critical complaints"
    assert all(item["destination"].startswith("/") for item in center["items"])

    client.cookies.clear()
    auditor = login(client, "auditor@casesync.demo")
    forbidden = client.post("/api/v1/demo/sessions", headers=auditor, json={"scenario": "sla_escalation"})
    assert forbidden.status_code == 403


def test_sla_demo_persists_assignment_notifications_and_escalation(client, central):
    before_notifications = client.get("/api/v1/notifications").json()["items"]
    session = _run_scenario(client, central, "sla_escalation")
    complaint = client.get(f"/api/v1/complaints/{session['complaints'][0]['id']}").json()

    assert session["status"] == "completed"
    assert complaint["status"] == "escalated"
    assert complaint["assigned_officer"] is not None
    assert [row["type"] for row in complaint["journey"]][-1] == "escalate"
    sla_event = next(row for row in session["result"]["events"] if row["title"] == "SLA monitoring completed")
    assert sla_event["notifications_generated"] >= 0
    assert session["notifications"]
    assert session["audit_events"]
    assert len(client.get("/api/v1/notifications").json()["items"]) >= len(before_notifications)
