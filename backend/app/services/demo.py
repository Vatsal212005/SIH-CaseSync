from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Bureau,
    AuditEvent,
    CaseStatus,
    Complaint,
    ComplaintAction,
    ComplaintCategory,
    CoordinationActionItem,
    CoordinationComplaint,
    CoordinationParticipant,
    CoordinationRecord,
    DemoSession,
    Institution,
    Notification,
    OverlapFinding,
    OverlapReview,
    Priority,
    RelatedCaseLink,
    ReviewState,
    Role,
    User,
)
from app.ml.engine import MODEL_STATUS
from app.schemas import ActionInput
from app.services.audit import audit
from app.services.coordination import coordinate_finding
from app.services.overlap import analyze_pair, detect_overlaps
from app.services.sla import deadline_for, run_sla_check
from app.services.workflow import perform_action

SCENARIOS = {
    "duplicate_investigations": {
        "title": "AI detects duplicate investigations",
        "steps": [
            "Register canonical institution",
            "Receive PGRC complaint",
            "Receive Regulation Bureau complaint",
            "Run AI overlap analysis",
            "Record human review",
            "Create cross-bureau coordination",
        ],
    },
    "different_complaints": {
        "title": "Same institution, different complaints",
        "steps": [
            "Register canonical institution",
            "Receive fee complaint",
            "Receive infrastructure complaint",
            "Run AI distinction analysis",
            "Explain the computed outcome",
        ],
    },
    "sla_escalation": {
        "title": "SLA violation and escalation",
        "steps": [
            "Register canonical institution",
            "Receive deadline-sensitive complaint",
            "Assign an accountable officer",
            "Run SLA monitoring",
            "Escalate the complaint",
        ],
    },
}


def _required(name: str, rows: list) -> object:
    for row in rows:
        if getattr(row, "name", None) == name or getattr(row, "code", None) == name:
            return row
    raise HTTPException(409, f"Demo prerequisite '{name}' is unavailable")


def start_session(db: Session, scenario: str, user: User) -> DemoSession:
    if not settings.demo_mode:
        raise HTTPException(404, "Interactive demos are disabled")
    if scenario not in SCENARIOS:
        raise HTTPException(422, "Unknown demonstration scenario")
    # Keep recovery unambiguous: a user may have one active studio run at a
    # time. Starting another run archives only that user's demo sessions and
    # never alters the synthetic records created by an earlier run.
    now = datetime.now(timezone.utc)
    for active in (
        db.query(DemoSession)
        .filter(DemoSession.created_by_id == user.id, DemoSession.status == "active")
        .all()
    ):
        active.status = "archived"
        active.archived_at = now
        audit(db, user.id, "demo.archived", "demo_session", active.id, after={"reason": "new_session"})
    session = DemoSession(scenario=scenario, created_by_id=user.id, complaint_ids=[], result_json={"events": []})
    db.add(session)
    db.flush()
    audit(db, user.id, "demo.started", "demo_session", session.id, after={"scenario": scenario})
    db.commit()
    db.refresh(session)
    return session


def restart_session(db: Session, session: DemoSession, user: User) -> DemoSession:
    if session.created_by_id != user.id and user.role not in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN}:
        raise HTTPException(403, "Demo session access denied")
    session.status = "archived"
    session.archived_at = datetime.now(timezone.utc)
    audit(db, user.id, "demo.archived", "demo_session", session.id)
    db.commit()
    return start_session(db, session.scenario, user)


def _institution(db: Session, session: DemoSession) -> Institution:
    suffix = session.id.split("-")[0].upper()
    names = {
        "duplicate_investigations": "Saraswati Institute of Applied Technology",
        "different_complaints": "National Institute of Emerging Engineering",
        "sla_escalation": "Vivekananda College of Technical Studies",
    }
    institution = Institution(
        permanent_id=f"SIH-DEMO-{suffix}",
        name=f"{names[session.scenario]} ({suffix})",
        normalized_name=f"sih demo {suffix.lower()}",
        address="Innovation Avenue, Synthetic Education District",
        city="New Delhi",
        state="Delhi",
        region="Northern",
        postal_code="110001",
        institution_type="College of Engineering",
        approval_status="Approved",
        contact_email=f"demo-{suffix.lower()}@example.invalid",
        is_synthetic=True,
    )
    db.add(institution)
    db.flush()
    session.institution_id = institution.id
    return institution


def _received_for_approaching_deadline(db: Session, category_id: str, bureau_id: str) -> date:
    today = date.today()
    for age in range(1, 120):
        received = today - timedelta(days=age)
        deadline = deadline_for(db, category_id, Priority.HIGH, bureau_id, received)
        remaining = (deadline.date() - today).days
        if 0 <= remaining <= 2:
            return received
    return today - timedelta(days=14)


def _new_complaint(
    db: Session,
    session: DemoSession,
    user: User,
    institution: Institution,
    *,
    bureau: Bureau,
    category: ComplaintCategory,
    title: str,
    description: str,
    priority: Priority = Priority.HIGH,
    assigned_officer_id: str | None = None,
    date_received: date | None = None,
    # Demo complaint-entry steps must stay fast and deterministic. The scenario
    # runs embedding inference explicitly in its analysis step, where the UI can
    # explain model warm-up and display the resulting evidence.
    run_overlap: bool = False,
) -> Complaint:
    seq = (db.query(Complaint).count() or 0) + 1
    received = date_received or date.today()
    complaint = Complaint(
        complaint_no=f"CMP-{date.today().year}-{seq:06d}",
        institution_id=institution.id,
        title=title,
        description=description,
        category_id=category.id,
        priority=priority,
        source=f"SIH Demo {session.id[:8]}",
        stakeholder_type="Synthetic evaluator scenario",
        date_received=received,
        originating_bureau_id=bureau.id,
        assigned_bureau_id=bureau.id,
        assigned_officer_id=assigned_officer_id,
        status=CaseStatus.PENDING,
        created_by_id=user.id,
        is_synthetic=True,
    )
    complaint.sla_deadline = deadline_for(db, category.id, priority, bureau.id, received)
    db.add(complaint)
    db.flush()
    db.add(ComplaintAction(
        complaint_id=complaint.id,
        actor_id=user.id,
        action_type="registered",
        to_status=CaseStatus.PENDING.value,
        to_bureau_id=bureau.id,
        remarks=f"Created by isolated SIH demo session {session.id[:8]}",
        metadata_json={"demo_session_id": session.id},
    ))
    session.complaint_ids = [*session.complaint_ids, complaint.id]
    if run_overlap:
        detect_overlaps(db, complaint)
    return complaint


def _pair_finding(db: Session, first_id: str, second_id: str) -> OverlapFinding | None:
    return db.query(OverlapFinding).filter(or_(
        (OverlapFinding.complaint_a_id == first_id) & (OverlapFinding.complaint_b_id == second_id),
        (OverlapFinding.complaint_a_id == second_id) & (OverlapFinding.complaint_b_id == first_id),
    )).order_by(OverlapFinding.detected_at.desc()).first()


def _event(session: DemoSession, title: str, detail: str, **data) -> None:
    result = dict(session.result_json or {})
    events = list(result.get("events", []))
    events.append({"step": session.current_step + 1, "title": title, "detail": detail, "at": datetime.now(timezone.utc).isoformat(), **data})
    result["events"] = events
    session.result_json = result


def _analysis(session: DemoSession, value: dict) -> None:
    result = dict(session.result_json or {})
    result["analysis"] = value
    session.result_json = result


def advance_session(db: Session, session: DemoSession, user: User, expected_step: int) -> DemoSession:
    if session.status != "active":
        return session
    if session.created_by_id != user.id and user.role not in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN}:
        raise HTTPException(403, "Demo session access denied")
    if expected_step != session.current_step:
        return session

    bureaus = db.query(Bureau).filter(Bureau.active.is_(True)).all()
    categories = db.query(ComplaintCategory).filter(ComplaintCategory.active.is_(True)).all()
    pgrc = _required("PGRC", bureaus)
    regulation = _required("RB", bureaus)
    approval = _required("AB", bureaus)
    fee = _required("Unauthorized fee collection", categories)
    infrastructure = _required("Infrastructure deficiencies", categories)
    compliance = _required("Institutional compliance", categories)
    institution = db.get(Institution, session.institution_id) if session.institution_id else None

    if session.current_step == 0:
        institution = _institution(db, session)
        _event(session, "Synthetic institution created", f"{institution.name} is isolated to this demo session.", institution_id=institution.id)
    elif session.scenario == "duplicate_investigations":
        if session.current_step == 1:
            complaint = _new_complaint(
                db, session, user, institution, bureau=pgrc, category=fee,
                title="Students charged an unapproved examination processing levy",
                description="Students report that the institution collected an additional mandatory examination processing levy not shown in the approved fee schedule. They request refund and regulatory review of the unauthorized charge.",
            )
            _event(session, "PGRC complaint registered", "The first active case now belongs to the Public Grievance Redressal Cell.", complaint_id=complaint.id)
        elif session.current_step == 2:
            complaint = _new_complaint(
                db, session, user, institution, bureau=regulation, category=fee,
                title="Institution collecting extra mandatory exam-related charges",
                description="A differently worded submission alleges compulsory extra money was collected from candidates for examination processing beyond the institution's approved fee structure. Regulatory verification and student reimbursement are requested.",
                run_overlap=False,
            )
            _event(session, "Regulation Bureau complaint registered", "A second active case now exists with different wording and separate bureau ownership.", complaint_id=complaint.id)
        elif session.current_step == 3:
            first, second = [db.get(Complaint, complaint_id) for complaint_id in session.complaint_ids]
            analysis = analyze_pair(db, first, second)
            detect_overlaps(db, second)
            finding = _pair_finding(db, session.complaint_ids[0], session.complaint_ids[1])
            session.finding_id = finding.id if finding else None
            analysis["finding_persisted"] = finding is not None
            analysis["finding_id"] = finding.id if finding else None
            _analysis(session, analysis)
            _event(
                session,
                "MiniLM overlap evaluation completed",
                "The real overlap engine evaluated the two descriptions; no outcome is hardcoded.",
                finding_id=finding.id if finding else None,
                semantic_score=analysis["semantic"],
                classification=analysis["finding_type"],
            )
        elif session.current_step == 4:
            finding = db.get(OverlapFinding, session.finding_id) if session.finding_id else None
            if not finding:
                _event(session, "No reviewable relationship found", "The live model did not produce a finding for this session.")
            elif finding.review_state == ReviewState.PENDING:
                raise HTTPException(409, "Record an explicit human review decision before continuing")
            else:
                review = db.query(OverlapReview).filter_by(finding_id=finding.id).order_by(OverlapReview.created_at.desc()).first()
                _event(
                    session,
                    f"Human review recorded: {finding.review_state.value.replace('_', ' ')}",
                    "The authorized review is separate from the model output and preserves the original score.",
                    review_state=finding.review_state.value,
                    reviewer_id=finding.reviewer_id,
                    review_id=review.id if review else None,
                )
                if finding.review_state != ReviewState.CONFIRMED:
                    session.current_step = len(SCENARIOS[session.scenario]["steps"])
                    session.status = "completed"
        elif session.current_step == 5:
            finding = db.get(OverlapFinding, session.finding_id)
            record = db.query(CoordinationRecord).filter_by(source_finding_id=finding.id).first()
            if not record:
                raise HTTPException(409, "Create the coordination record before continuing")
            session.coordination_id = record.id
            _event(session, "Coordination record created", "Both complaints remain separate records and now share owned actions, participants and a due date.", coordination_id=record.id)
    elif session.scenario == "different_complaints":
        if session.current_step == 1:
            complaint = _new_complaint(
                db, session, user, institution, bureau=pgrc, category=fee,
                title="Unapproved student development fee collected",
                description="Students allege collection of a compulsory development fee that is absent from the approved institutional fee schedule and request reimbursement.",
            )
            _event(session, "Fee complaint registered", "The allegation concerns student charges.", complaint_id=complaint.id)
        elif session.current_step == 2:
            complaint = _new_complaint(
                db, session, user, institution, bureau=approval, category=infrastructure,
                title="Core engineering laboratories lack required equipment",
                description="The mechanical and electrical laboratories reportedly lack calibrated instruments, safety equipment and functional workstations required for practical instruction.",
                run_overlap=False,
            )
            _event(session, "Infrastructure complaint registered", "A distinct allegation is owned by the Approval Bureau under the same canonical institution.", complaint_id=complaint.id)
        elif session.current_step == 3:
            first, second = [db.get(Complaint, complaint_id) for complaint_id in session.complaint_ids]
            analysis = analyze_pair(db, first, second)
            detect_overlaps(db, second)
            finding = _pair_finding(db, session.complaint_ids[0], session.complaint_ids[1])
            session.finding_id = finding.id if finding else None
            analysis["finding_persisted"] = finding is not None
            analysis["finding_id"] = finding.id if finding else None
            _analysis(session, analysis)
            _event(
                session,
                "Same-institution evaluation completed",
                "The engine distinguishes shared institutional activity from semantic duplication.",
                finding_id=finding.id if finding else None,
                semantic_score=analysis["semantic"],
                classification=analysis["finding_type"],
            )
        elif session.current_step == 4:
            analysis = (session.result_json or {}).get("analysis") or {}
            explanation = "These cases share a canonical institution but concern different allegations."
            explanation += f" The actual engine classified the relationship as {analysis.get('finding_type', 'unavailable').replace('_', ' ')} with semantic similarity {analysis.get('semantic', 0):.0%}."
            _event(session, "False-positive control explained", explanation, reviewable_finding=bool(analysis.get("finding_persisted")))
    else:
        if session.current_step == 1:
            received = _received_for_approaching_deadline(db, compliance.id, regulation.id)
            complaint = _new_complaint(
                db, session, user, institution, bureau=regulation, category=compliance,
                title="Required compliance disclosure remains unresolved",
                description="A synthetic compliance disclosure request remains unresolved as its configured disposal deadline approaches and requires accountable assignment.",
                date_received=received,
            )
            _event(session, "Deadline-sensitive complaint registered", "The deadline is calculated by the configured SLA policy.", complaint_id=complaint.id, sla_deadline=complaint.sla_deadline.isoformat())
        elif session.current_step == 2:
            complaint = db.get(Complaint, session.complaint_ids[0])
            officer = db.query(User).filter(User.role == Role.CASE_OFFICER, User.bureau_id == complaint.assigned_bureau_id, User.active.is_(True)).first()
            if not officer:
                raise HTTPException(409, "No active officer is available for the demo bureau")
            perform_action(db, complaint, user, ActionInput(action="assign", remarks="Assigned through the SIH SLA accountability demonstration.", officer_id=officer.id, destination_bureau_id=None))
            _event(session, "Officer assigned", f"{officer.full_name} now owns the next action.", officer_id=officer.id)
        elif session.current_step == 3:
            complaint = db.get(Complaint, session.complaint_ids[0])
            before_ids = {row.id for row in db.query(Notification).filter_by(related_type="complaint", related_id=complaint.id).all()}
            sla_result = run_sla_check(db)
            notifications = db.query(Notification).filter_by(related_type="complaint", related_id=complaint.id).order_by(Notification.created_at.desc()).all()
            new_ids = [row.id for row in notifications if row.id not in before_ids]
            _event(session, "SLA monitoring completed", "The idempotent SLA service evaluated the configured deadline and recipient rules.", notifications_generated=sla_result["generated"], notification_ids=new_ids, notifications_existing=len(notifications), complaint_id=complaint.id)
        elif session.current_step == 4:
            complaint = db.get(Complaint, session.complaint_ids[0])
            previous = complaint.status.value
            perform_action(db, complaint, user, ActionInput(action="escalate", remarks="Escalated after the configured SLA warning during the synthetic demonstration.", officer_id=None, destination_bureau_id=None))
            _event(session, "Complaint escalation recorded", "The complaint status, action history and audit evidence were updated by the real workflow service.", complaint_id=complaint.id, previous_status=previous, new_status=complaint.status.value)

    if session.status == "active":
        session.current_step += 1
    if session.current_step >= len(SCENARIOS[session.scenario]["steps"]):
        session.status = "completed"
    session.updated_at = datetime.now(timezone.utc)
    audit(db, user.id, "demo.advanced", "demo_session", session.id, after={"step": session.current_step, "status": session.status})
    db.commit()
    db.refresh(session)
    return session


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def session_payload(db: Session, session: DemoSession, viewer: User | None = None) -> dict:
    complaint_ids = session.complaint_ids or []
    rows = db.query(Complaint).filter(Complaint.id.in_(complaint_ids)).all() if complaint_ids else []
    by_id = {row.id: row for row in rows}
    complaints = [by_id[row_id] for row_id in complaint_ids if row_id in by_id]
    institution = db.get(Institution, session.institution_id) if session.institution_id else None
    finding = db.get(OverlapFinding, session.finding_id) if session.finding_id else None
    coordination = db.get(CoordinationRecord, session.coordination_id) if session.coordination_id else None
    if not coordination and finding:
        coordination = db.query(CoordinationRecord).filter_by(source_finding_id=finding.id).first()
    review = db.query(OverlapReview).filter_by(finding_id=finding.id).order_by(OverlapReview.created_at.desc()).first() if finding else None

    relevant_ids = {session.id, *complaint_ids}
    if session.institution_id:
        relevant_ids.add(session.institution_id)
    if finding:
        relevant_ids.add(finding.id)
    if coordination:
        relevant_ids.add(coordination.id)
    audits = db.query(AuditEvent).filter(AuditEvent.entity_id.in_(relevant_ids), AuditEvent.created_at >= session.created_at).order_by(AuditEvent.created_at).all()
    notification_query = db.query(Notification).filter(Notification.created_at >= session.created_at)
    related_ids = {*(complaint_ids or [])}
    if finding:
        related_ids.add(finding.id)
    if coordination:
        related_ids.add(coordination.id)
    notification_query = notification_query.filter(Notification.related_id.in_(related_ids)) if related_ids else notification_query.filter(False)
    if viewer and viewer.role not in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN}:
        notification_query = notification_query.filter(Notification.recipient_id == viewer.id)
    notifications = notification_query.order_by(Notification.created_at).all()

    participant_rows = db.query(CoordinationParticipant).filter_by(coordination_id=coordination.id).all() if coordination else []
    action_rows = db.query(CoordinationActionItem).filter_by(coordination_id=coordination.id).order_by(CoordinationActionItem.created_at).all() if coordination else []
    linked_ids = [row.complaint_id for row in db.query(CoordinationComplaint).filter_by(coordination_id=coordination.id).all()] if coordination else []
    owner = db.get(User, coordination.owner_id) if coordination else None

    complaint_payload = []
    for row in complaints:
        actions = db.query(ComplaintAction).filter_by(complaint_id=row.id).order_by(ComplaintAction.created_at).all()
        complaint_payload.append({
            "id": row.id,
            "complaint_no": row.complaint_no,
            "title": row.title,
            "description": row.description,
            "category": {"id": row.category.id, "name": row.category.name},
            "priority": row.priority.value,
            "status": row.status.value,
            "source": row.source,
            "stakeholder_type": row.stakeholder_type,
            "date_received": row.date_received.isoformat(),
            "created_at": _iso(row.created_at),
            "sla_deadline": _iso(row.sla_deadline),
            "sla_days": (row.sla_deadline.date() - row.date_received).days if row.sla_deadline else None,
            "days_remaining": (row.sla_deadline.date() - date.today()).days if row.sla_deadline else None,
            "bureau": {"id": row.assigned_bureau.id, "code": row.assigned_bureau.code, "name": row.assigned_bureau.name},
            "assigned_officer": ({"id": row.assigned_officer.id, "name": row.assigned_officer.full_name, "role": row.assigned_officer.role.value} if row.assigned_officer else None),
            "institution": ({"id": institution.id, "name": institution.name, "permanent_id": institution.permanent_id} if institution else None),
            "actions": [{
                "id": action.id,
                "type": action.action_type,
                "actor": action.actor.full_name,
                "from_status": action.from_status,
                "to_status": action.to_status,
                "remarks": action.remarks,
                "at": _iso(action.created_at),
            } for action in actions],
        })

    return {
        "id": session.id,
        "scenario": session.scenario,
        "title": SCENARIOS[session.scenario]["title"],
        "steps": SCENARIOS[session.scenario]["steps"],
        "status": session.status,
        "current_step": session.current_step,
        "institution_id": session.institution_id,
        "institution": ({
            "id": institution.id,
            "permanent_id": institution.permanent_id,
            "name": institution.name,
            "address": institution.address,
            "city": institution.city,
            "state": institution.state,
            "region": institution.region,
            "postal_code": institution.postal_code,
            "institution_type": institution.institution_type,
            "approval_status": institution.approval_status,
            "is_synthetic": institution.is_synthetic,
            "created_at": _iso(institution.created_at),
        } if institution else None),
        "complaints": complaint_payload,
        "analysis": (session.result_json or {}).get("analysis"),
        "ai_runtime": {**MODEL_STATUS, "embedding_dimensions": 384},
        "finding": ({
            "id": finding.id,
            "type": finding.finding_type,
            "semantic_score": finding.similarity_score,
            "hybrid_score": finding.hybrid_score,
            "severity": finding.severity,
            "review_state": finding.review_state.value,
            "reasons": finding.reasons,
            "recommendation": finding.recommendation,
            "detected_at": _iso(finding.detected_at),
            "review": ({
                "id": review.id,
                "decision": review.decision,
                "notes": review.notes,
                "reviewer_id": review.reviewer_id,
                "reviewer_name": db.get(User, review.reviewer_id).full_name,
                "reviewed_at": _iso(review.created_at),
            } if review else None),
        } if finding else None),
        "coordination": ({
            "id": coordination.id,
            "title": coordination.title,
            "status": coordination.status,
            "summary": coordination.summary,
            "owner_id": coordination.owner_id,
            "owner_name": owner.full_name if owner else None,
            "target_date": _iso(coordination.target_date),
            "created_at": _iso(coordination.created_at),
            "complaint_ids": linked_ids,
            "participants": [{
                "bureau_id": participant.bureau_id,
                "bureau_name": db.get(Bureau, participant.bureau_id).name,
                "officer_id": participant.user_id,
                "officer_name": db.get(User, participant.user_id).full_name if participant.user_id else None,
            } for participant in participant_rows],
            "actions": [{
                "id": action.id,
                "title": action.title,
                "assignee_id": action.assignee_id,
                "assignee_name": db.get(User, action.assignee_id).full_name,
                "due_date": _iso(action.due_date),
                "completed": action.completed,
                "created_at": _iso(action.created_at),
            } for action in action_rows],
        } if coordination else None),
        "notifications": [{
            "id": row.id,
            "type": row.type,
            "title": row.title,
            "message": row.message,
            "recipient_id": row.recipient_id,
            "recipient_name": db.get(User, row.recipient_id).full_name,
            "destination": row.destination,
            "created_at": _iso(row.created_at),
        } for row in notifications],
        "audit_events": [{
            "id": row.id,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "actor_name": db.get(User, row.actor_id).full_name if row.actor_id else "System",
            "created_at": _iso(row.created_at),
        } for row in audits],
        "result": session.result_json or {},
        "created_at": _iso(session.created_at),
        "updated_at": _iso(session.updated_at),
        "archived_at": _iso(session.archived_at),
    }
