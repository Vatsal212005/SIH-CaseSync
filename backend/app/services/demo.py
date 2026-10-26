from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    Bureau,
    CaseStatus,
    Complaint,
    ComplaintAction,
    ComplaintCategory,
    CoordinationActionItem,
    CoordinationParticipant,
    CoordinationRecord,
    DemoSession,
    Institution,
    OverlapFinding,
    OverlapReview,
    Priority,
    RelatedCaseLink,
    ReviewState,
    Role,
    User,
)
from app.schemas import ActionInput
from app.services.audit import audit
from app.services.coordination import coordinate_finding
from app.services.overlap import detect_overlaps
from app.services.sla import deadline_for, run_sla_check
from app.services.workflow import perform_action

SCENARIOS = {
    "duplicate_investigations": {
        "title": "AI detects duplicate investigations",
        "steps": ["Create synthetic institution", "Register PGRC complaint", "Register Regulation Bureau complaint and run MiniLM", "Confirm evidence and coordinate"],
    },
    "different_complaints": {
        "title": "Same institution, different complaints",
        "steps": ["Create synthetic institution", "Register fee complaint", "Register infrastructure complaint and run MiniLM", "Explain the actual classification"],
    },
    "sla_escalation": {
        "title": "SLA violation and escalation",
        "steps": ["Create synthetic institution", "Register deadline-sensitive complaint", "Assign an accountable officer", "Run SLA scan and escalate"],
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
            )
            finding = _pair_finding(db, session.complaint_ids[0], complaint.id)
            session.finding_id = finding.id if finding else None
            _event(
                session,
                "MiniLM overlap evaluation completed",
                "The real overlap engine evaluated the two descriptions; no outcome is hardcoded.",
                finding_id=finding.id if finding else None,
                semantic_score=finding.similarity_score if finding else None,
                classification=finding.finding_type if finding else "no_reviewable_finding",
            )
        elif session.current_step == 3:
            finding = db.get(OverlapFinding, session.finding_id) if session.finding_id else None
            if not finding:
                _event(session, "No reviewable relationship found", "The live model did not produce a finding for this session.")
            else:
                finding.review_state = ReviewState.CONFIRMED
                finding.reviewer_id = user.id
                finding.resolution_notes = "Confirmed during the guided synthetic SIH demonstration after human review."
                db.add(OverlapReview(finding_id=finding.id, reviewer_id=user.id, decision=ReviewState.CONFIRMED.value, notes=finding.resolution_notes))
                ids = sorted([finding.complaint_a_id, finding.complaint_b_id])
                link = db.query(RelatedCaseLink).filter_by(complaint_a_id=ids[0], complaint_b_id=ids[1]).first()
                if not link:
                    db.add(RelatedCaseLink(complaint_a_id=ids[0], complaint_b_id=ids[1], relation_type=finding.finding_type, created_by_id=user.id, active=True, justification=finding.resolution_notes))
                record, _ = coordinate_finding(
                    db, finding, user,
                    next_action="Jointly verify the fee approval record and prepare a coordinated response",
                    remarks=finding.resolution_notes,
                    request_key=f"demo:{session.id}:coordination",
                )
                session.coordination_id = record.id
                _event(session, "Human review confirmed and coordination opened", "The cases are linked without merging or disposing either complaint.", coordination_id=record.id)
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
            )
            finding = _pair_finding(db, session.complaint_ids[0], complaint.id)
            session.finding_id = finding.id if finding else None
            _event(
                session,
                "Same-institution evaluation completed",
                "The engine distinguishes shared institutional activity from semantic duplication.",
                finding_id=finding.id if finding else None,
                semantic_score=finding.similarity_score if finding else None,
                classification=finding.finding_type if finding else "no_reviewable_finding",
            )
        elif session.current_step == 3:
            finding = db.get(OverlapFinding, session.finding_id) if session.finding_id else None
            explanation = "These cases share a canonical institution but concern different allegations."
            if finding:
                explanation += f" The actual engine classified the relationship as {finding.finding_type.replace('_', ' ')} with semantic similarity {finding.similarity_score:.0%}."
            _event(session, "Evidence explained", explanation)
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
            sla_result = run_sla_check(db)
            perform_action(db, complaint, user, ActionInput(action="escalate", remarks="Escalated after the configured SLA warning during the synthetic demonstration.", officer_id=None, destination_bureau_id=None))
            _event(session, "SLA scan and escalation recorded", "Persistent notifications and complaint history were updated by the real workflow services.", notifications_generated=sla_result["generated"], complaint_id=complaint.id)

    session.current_step += 1
    if session.current_step >= len(SCENARIOS[session.scenario]["steps"]):
        session.status = "completed"
    session.updated_at = datetime.now(timezone.utc)
    audit(db, user.id, "demo.advanced", "demo_session", session.id, after={"step": session.current_step, "status": session.status})
    db.commit()
    db.refresh(session)
    return session


def session_payload(db: Session, session: DemoSession) -> dict:
    complaints = db.query(Complaint).filter(Complaint.id.in_(session.complaint_ids or [])).all() if session.complaint_ids else []
    finding = db.get(OverlapFinding, session.finding_id) if session.finding_id else None
    coordination = db.get(CoordinationRecord, session.coordination_id) if session.coordination_id else None
    return {
        "id": session.id,
        "scenario": session.scenario,
        "title": SCENARIOS[session.scenario]["title"],
        "steps": SCENARIOS[session.scenario]["steps"],
        "status": session.status,
        "current_step": session.current_step,
        "institution_id": session.institution_id,
        "complaints": [{
            "id": row.id, "complaint_no": row.complaint_no, "title": row.title,
            "bureau": row.assigned_bureau.code, "status": row.status.value,
            "sla_deadline": row.sla_deadline.isoformat() if row.sla_deadline else None,
        } for row in complaints],
        "finding": ({
            "id": finding.id, "type": finding.finding_type, "semantic_score": finding.similarity_score,
            "hybrid_score": finding.hybrid_score, "severity": finding.severity,
            "review_state": finding.review_state.value, "reasons": finding.reasons,
        } if finding else None),
        "coordination": ({
            "id": coordination.id, "title": coordination.title, "target_date": coordination.target_date.isoformat() if coordination.target_date else None,
            "participants": db.query(CoordinationParticipant).filter_by(coordination_id=coordination.id).count(),
            "open_actions": db.query(CoordinationActionItem).filter_by(coordination_id=coordination.id, completed=False).count(),
        } if coordination else None),
        "result": session.result_json or {},
        "created_at": session.created_at.isoformat(),
    }
