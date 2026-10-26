from datetime import date

from app.tests.conftest import login


def test_health(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200 and r.json()["database"] == "connected"


def test_authentication_and_logout(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.post("/api/v1/auth/login", json={"email":"central@casesync.demo","password":"wrong-password"}).status_code == 401
    headers = login(client)
    assert client.get("/api/v1/auth/me").json()["role"] == "central_admin"
    assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200


def test_csrf_is_required(client):
    login(client)
    r = client.post("/api/v1/institutions", json={})
    assert r.status_code == 403


def test_dashboard_and_search_are_database_backed(client, central):
    dashboard = client.get("/api/v1/dashboard").json()
    assert dashboard["kpis"]["total"] == 1000
    result = client.get("/api/v1/search?q=CMP-2026-000001").json()
    assert result["complaints"][0]["complaint_no"] == "CMP-2026-000001"


def test_institution_uniqueness(client, central):
    original = client.get("/api/v1/institutions?page_size=1").json()["items"][0]
    payload = {k: original[k] for k in ["permanent_id","name","address","city","state","region","postal_code","institution_type","approval_status","contact_email","is_synthetic"]}
    payload["aliases"] = []
    assert client.post("/api/v1/institutions", headers=central, json=payload).status_code == 409


def test_csv_import_validation(client, central):
    body = b"permanent_id,name\nX,Incomplete\n"
    r = client.post("/api/v1/institutions/import", headers=central, files={"file":("institutions.csv", body, "text/csv")})
    assert r.status_code == 422


def test_csv_import_uses_row_savepoints(client, central):
    body = (
        "permanent_id,name,address,city,state,region,postal_code,institution_type,approval_status\n"
        "DEMO-IMPORT-OK,DEMO Imported Technical Institute,Synthetic Import Road,Pune,Maharashtra,Western,411001,Technical Institute,Approved\n"
        "DEMO-IMPORT-BAD,DEMO Broken Import,Synthetic Import Road,Pune,Maharashtra,Western,invalid,Technical Institute,Approved\n"
    ).encode()
    response = client.post("/api/v1/institutions/import", headers=central, files={"file": ("institutions.csv", body, "text/csv")})
    assert response.status_code == 200
    assert response.json()["created"] == 1 and len(response.json()["errors"]) == 1
    rows = client.get("/api/v1/institutions?q=DEMO-IMPORT-OK").json()["items"]
    assert rows and rows[0]["is_synthetic"] is False


def test_complaint_creation_and_computed_overlap(client, central):
    meta = client.get("/api/v1/meta").json()
    inst = client.get("/api/v1/institutions?page_size=1").json()["items"][0]
    category = next(x for x in meta["categories"] if x["name"] == "Unauthorized fee collection")
    payload = {"institution_id":inst["id"],"title":"Unapproved additional development charge","description":"Students report a mandatory additional development fee outside the approved schedule.","category_id":category["id"],"priority":"high","source":"Portal","stakeholder_type":"Student","date_received":str(date.today()),"assigned_bureau_id":meta["bureaus"][0]["id"],"assigned_officer_id":None}
    first = client.post("/api/v1/complaints", headers=central, json=payload)
    assert first.status_code == 200
    payload.update(title="Unauthorized extra student fees", description="An unapproved development amount was collected from enrolled students as a mandatory charge.", assigned_bureau_id=meta["bureaus"][1]["id"])
    second = client.post("/api/v1/complaints", headers=central, json=payload)
    assert second.status_code == 200
    findings = client.get("/api/v1/overlaps?state=pending&page_size=100").json()["items"]
    assert any(second.json()["id"] in {x["complaint_a"]["id"],x["complaint_b"]["id"]} for x in findings)


def test_invalid_transition_and_action_history(client, central):
    case = client.get("/api/v1/complaints?status=pending&page_size=1").json()["items"][0]
    r = client.post(f"/api/v1/complaints/{case['id']}/actions", headers=central, json={"action":"dispose","remarks":"Cannot dispose directly"})
    assert r.status_code == 409
    r = client.post(f"/api/v1/complaints/{case['id']}/actions", headers=central, json={"action":"start","remarks":"Started formal review"})
    assert r.status_code == 200 and r.json()["status"] == "under_process"
    detail = client.get(f"/api/v1/complaints/{case['id']}").json()
    assert any(x["type"] == "start" for x in detail["actions"])


def test_bureau_authorization(client):
    headers = login(client, "officer1.rb@casesync.demo")
    current = client.get("/api/v1/auth/me").json()
    meta = client.get("/api/v1/meta").json()
    institution = client.get("/api/v1/institutions?page_size=1").json()["items"][0]
    own_bureau = next(x for x in meta["bureaus"] if x["id"] == current["bureau_id"])
    created = client.post(
        "/api/v1/complaints",
        headers=headers,
        json={"institution_id": institution["id"], "title": "Officer registered synthetic complaint", "description": "A synthetic complaint registered to verify least-privilege officer assignment.", "category_id": meta["categories"][0]["id"], "priority": "medium", "source": "Portal", "stakeholder_type": "Student", "date_received": str(date.today()), "assigned_bureau_id": own_bureau["id"], "assigned_officer_id": None},
    )
    assert created.status_code == 200 and created.json()["assigned_officer"]["id"] == current["id"]
    other_case = client.get("/api/v1/complaints?page_size=100").json()["items"]
    own = next(x for x in other_case if x["assigned_officer"] and "RB Officer 1" in x["assigned_officer"]["name"])
    # Case officers may view their bureau but may mutate only assigned cases.
    r = client.post(f"/api/v1/complaints/{own['id']}/actions", headers=headers, json={"action":"remark","remarks":"Officer review note"})
    assert r.status_code == 200
    client.cookies.clear(); headers = login(client, "auditor@casesync.demo")
    assert client.post(f"/api/v1/complaints/{own['id']}/actions", headers=headers, json={"action":"remark","remarks":"Unauthorized"}).status_code == 403


def test_overlap_human_review_creates_coordination(client, central):
    rows = client.get("/api/v1/overlaps?state=pending&page_size=100").json()["items"]
    assert rows
    r = client.post(f"/api/v1/overlaps/{rows[0]['id']}/review", headers=central, json={"decision":"confirmed","notes":"Related synthetic cases require coordinated evidence review.","create_coordination":True})
    assert r.status_code == 200 and r.json()["coordination_id"]
    assert any(x["id"] == r.json()["coordination_id"] for x in client.get("/api/v1/coordination").json())


def test_notifications_and_sla_deduplication(client, central):
    first = client.post("/api/v1/admin/run-sla", headers=central).json()
    second = client.post("/api/v1/admin/run-sla", headers=central).json()
    assert first["generated"] >= 0 and second["generated"] == 0
    notes = client.get("/api/v1/notifications").json()
    assert notes["items"]
    assert client.post("/api/v1/notifications/read", headers=central, json={"ids":None}).status_code == 200


def test_report_exports_reconcile(client, central):
    summary = client.get("/api/v1/reports/summary?status=disposed").json()
    csv_response = client.get("/api/v1/reports/export.csv?status=disposed")
    assert csv_response.status_code == 200
    assert len(csv_response.text.strip().splitlines()) - 1 == summary["total"]
    pdf = client.get("/api/v1/reports/export.pdf?status=disposed")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")


def test_all_named_reports_are_computed(client, central):
    report_types = ["institution_history", "bureau_workload", "region_statistics", "state_distribution", "pending_ageing", "disposal_rate", "sla_compliance", "overlap_cases", "officer_workload", "monthly_performance", "quarterly_performance", "transfer_escalation"]
    for report_type in report_types:
        response = client.get(f"/api/v1/reports/summary?report_type={report_type}")
        assert response.status_code == 200
        assert response.json()["report_type"] == report_type
        assert isinstance(response.json()["report_rows"], list)


def test_admin_user_endpoint_is_admin_only(client, central):
    assert client.get("/api/v1/admin/users").status_code == 403
    client.cookies.clear(); login(client, "admin@casesync.demo")
    assert client.get("/api/v1/admin/users").status_code == 200


def test_complaint_edit_link_and_unlink_are_persistent(client, central):
    cases = client.get("/api/v1/complaints?page_size=100").json()["items"]
    first = next(x for x in cases if x["status"] != "disposed")
    detail = client.get(f"/api/v1/complaints/{first['id']}").json()
    already_linked = {x["complaint_a_id"] if x["complaint_a_id"] != first["id"] else x["complaint_b_id"] for x in detail["related_cases"]}
    second = next(x for x in cases if x["id"] != first["id"] and x["id"] not in already_linked)
    edit = {
        "title": "Updated synthetic complaint title",
        "description": "Updated synthetic complaint narrative with enough detail for overlap re-evaluation.",
        "category_id": detail["category_id"],
        "priority": "high",
        "next_action": "Verify the updated synthetic evidence",
    }
    response = client.put(f"/api/v1/complaints/{first['id']}", headers=central, json=edit)
    assert response.status_code == 200
    updated = client.get(f"/api/v1/complaints/{first['id']}").json()
    assert updated["title"] == edit["title"]
    assert any(action["type"] == "edited" for action in updated["actions"])

    linked = client.post(
        f"/api/v1/complaints/{first['id']}/links",
        headers=central,
        json={"other_complaint_id": second["id"], "relation_type": "related", "justification": "Synthetic relationship verification"},
    )
    assert linked.status_code == 200
    assert any(x["id"] == linked.json()["id"] for x in client.get(f"/api/v1/complaints/{first['id']}").json()["related_cases"])
    removed = client.delete(
        f"/api/v1/complaints/{first['id']}/links/{linked.json()['id']}?justification=Confirmed%20as%20unrelated",
        headers=central,
    )
    assert removed.status_code == 200 and removed.json()["active"] is False


def test_coordination_actions_and_bureau_scope(client, central):
    records = client.get("/api/v1/coordination").json()
    record = records[0]
    meta = client.get("/api/v1/meta").json()
    officer = meta["officers"][0]
    created = client.post(
        f"/api/v1/coordination/{record['id']}/actions",
        headers=central,
        json={"title": "Validate synthetic coordination evidence", "assignee_id": officer["id"], "due_date": str(date.today())},
    )
    assert created.status_code == 200
    completed = client.patch(f"/api/v1/coordination/actions/{created.json()['id']}", headers=central, json={"completed": True})
    assert completed.status_code == 200 and completed.json()["completed"] is True

    non_participant = next(b for b in meta["bureaus"] if b["id"] not in record["participants"])
    client.cookies.clear(); login(client, f"officer1.{non_participant['code'].lower()}@casesync.demo")
    visible_ids = {x["id"] for x in client.get("/api/v1/coordination").json()}
    assert record["id"] not in visible_ids


def test_transfer_notifies_receiving_bureau(client, central):
    case = client.get("/api/v1/complaints?status=under_process&page_size=1").json()["items"][0]
    meta = client.get("/api/v1/meta").json()
    destination = next(b for b in meta["bureaus"] if b["id"] != case["assigned_bureau"]["id"])
    response = client.post(
        f"/api/v1/complaints/{case['id']}/actions",
        headers=central,
        json={"action": "transfer", "remarks": "Transfer for synthetic cross-bureau verification", "destination_bureau_id": destination["id"]},
    )
    assert response.status_code == 200 and response.json()["assigned_bureau_id"] == destination["id"]
    client.cookies.clear(); login(client, f"head.{destination['code'].lower()}@casesync.demo")
    notifications = client.get("/api/v1/notifications").json()["items"]
    assert any(x["type"] == "transfer" and x["related_id"] == case["id"] for x in notifications)


def test_admin_configuration_mutations(client):
    headers = login(client, "admin@casesync.demo")
    bureau = client.post("/api/v1/admin/bureaus", headers=headers, json={"code": "DEMOX", "name": "Demo Integration Bureau", "active": True})
    assert bureau.status_code == 200
    category = client.post("/api/v1/admin/categories", headers=headers, json={"name": "Synthetic data verification", "active": True})
    assert category.status_code == 200
    user = client.post(
        "/api/v1/admin/users",
        headers=headers,
        json={"email": "configured.user@casesync.demo", "full_name": "Configured Demo User", "password": "Configured@2026", "role": "case_officer", "bureau_id": bureau.json()["id"]},
    )
    assert user.status_code == 200
    settings = client.put(
        "/api/v1/admin/settings/overlap_thresholds",
        headers=headers,
        json={"value": {"shared_activity": 0.4, "related": 0.56, "likely_duplicate": 0.84}},
    )
    assert settings.status_code == 200 and settings.json()["value"]["related"] == 0.56


def test_direct_overlap_access_is_bureau_scoped(client, central):
    rows = client.get("/api/v1/overlaps?page_size=100").json()["items"]
    outside_rb = next(x for x in rows if "RB" not in {x["complaint_a"]["assigned_bureau"]["code"], x["complaint_b"]["assigned_bureau"]["code"]})
    client.cookies.clear(); login(client, "officer1.rb@casesync.demo")
    assert client.get(f"/api/v1/overlaps/{outside_rb['id']}").status_code == 403


def test_password_change_requires_current_password(client):
    headers = login(client, "officer3.swc@casesync.demo")
    rejected = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "not-the-password", "new_password": "A-New-Demo@2026"})
    assert rejected.status_code == 422
    changed = client.post("/api/v1/auth/change-password", headers=headers, json={"current_password": "CaseSync@2026", "new_password": "A-New-Demo@2026"})
    assert changed.status_code == 200
    client.cookies.clear()
    response = client.post("/api/v1/auth/login", json={"email": "officer3.swc@casesync.demo", "password": "A-New-Demo@2026"})
    assert response.status_code == 200

