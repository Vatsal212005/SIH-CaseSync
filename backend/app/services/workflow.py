from datetime import date, datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import Bureau, CaseStatus, Complaint, ComplaintAction, Role, User
from app.services.audit import audit, notify

TRANSITIONS = {
    "start": ({CaseStatus.PENDING, CaseStatus.REOPENED}, CaseStatus.UNDER_PROCESS),
    "transfer": ({CaseStatus.PENDING, CaseStatus.UNDER_PROCESS, CaseStatus.ESCALATED, CaseStatus.REOPENED}, CaseStatus.TRANSFERRED),
    "accept_transfer": ({CaseStatus.TRANSFERRED}, CaseStatus.UNDER_PROCESS),
    "escalate": ({CaseStatus.PENDING, CaseStatus.UNDER_PROCESS, CaseStatus.REOPENED}, CaseStatus.ESCALATED),
    "dispose": ({CaseStatus.UNDER_PROCESS, CaseStatus.ESCALATED, CaseStatus.REOPENED}, CaseStatus.DISPOSED),
    "reopen": ({CaseStatus.DISPOSED}, CaseStatus.REOPENED),
}


def perform_action(db: Session, complaint: Complaint, actor: User, payload) -> Complaint:
    old_status = complaint.status
    old_bureau = complaint.assigned_bureau_id
    if payload.action in TRANSITIONS:
        allowed, target = TRANSITIONS[payload.action]
        if complaint.status not in allowed:
            raise HTTPException(409, f"Cannot {payload.action} a {complaint.status.value} complaint")
        complaint.status = target
    if payload.action == "transfer":
        if not payload.destination_bureau_id or payload.destination_bureau_id == old_bureau:
            raise HTTPException(422, "A different destination bureau is required")
        destination = db.get(Bureau, payload.destination_bureau_id)
        if not destination or not destination.active:
            raise HTTPException(422, "Destination bureau must be active")
        complaint.assigned_bureau_id = payload.destination_bureau_id
        complaint.assigned_officer_id = None
        for head in db.query(User).filter(User.role == Role.BUREAU_HEAD, User.bureau_id == payload.destination_bureau_id, User.active.is_(True)).all():
            notify(db, head.id, "transfer", "Complaint transfer received", f"{complaint.complaint_no} was transferred to your bureau.", "complaint", complaint.id, f"/complaints/{complaint.id}")
    if payload.action == "assign":
        if actor.role not in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD}:
            raise HTTPException(403, "Only administrators and bureau heads can assign cases")
        officer = db.get(User, payload.officer_id) if payload.officer_id else None
        if not officer or not officer.active or officer.role != Role.CASE_OFFICER or officer.bureau_id != complaint.assigned_bureau_id:
            raise HTTPException(422, "Officer must be active in the assigned bureau")
        complaint.assigned_officer_id = officer.id
        notify(db, officer.id, "assignment", "Complaint assigned", f"You were assigned {complaint.complaint_no}.", "complaint", complaint.id, f"/complaints/{complaint.id}")
    if payload.action == "dispose":
        complaint.disposal_date, complaint.disposal_remarks = date.today(), payload.remarks
    if payload.action == "reopen":
        complaint.disposal_date, complaint.disposal_remarks = None, None
    if payload.action == "escalate":
        for admin in db.query(User).filter(User.role.in_([Role.CENTRAL_ADMIN, Role.BUREAU_HEAD]), User.active.is_(True)).all():
            if admin.role == Role.CENTRAL_ADMIN or admin.bureau_id == complaint.assigned_bureau_id:
                notify(db, admin.id, "escalation", "Complaint escalated", f"{complaint.complaint_no} requires escalated review.", "complaint", complaint.id, f"/complaints/{complaint.id}")
    complaint.latest_action = payload.remarks[:300]
    complaint.last_action_at = datetime.now(timezone.utc)
    complaint.version += 1
    db.add(ComplaintAction(complaint_id=complaint.id, actor_id=actor.id, action_type=payload.action, from_status=old_status.value, to_status=complaint.status.value, from_bureau_id=old_bureau, to_bureau_id=complaint.assigned_bureau_id, remarks=payload.remarks))
    audit(db, actor.id, f"complaint.{payload.action}", "complaint", complaint.id, {"status": old_status.value, "bureau_id": old_bureau}, {"status": complaint.status.value, "bureau_id": complaint.assigned_bureau_id})
    return complaint

