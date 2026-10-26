from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.models import CaseStatus, Complaint, Role, SlaPolicy, User
from app.services.audit import notify


def deadline_for(db: Session, category_id: str, priority, bureau_id: str, received) -> datetime:
    policy = db.query(SlaPolicy).filter(SlaPolicy.active.is_(True), SlaPolicy.priority == priority, SlaPolicy.category_id.in_([category_id, None]), SlaPolicy.bureau_id.in_([bureau_id, None])).order_by(SlaPolicy.category_id.desc(), SlaPolicy.bureau_id.desc()).first()
    days = policy.days if policy else {"low": 45, "medium": 30, "high": 15, "critical": 7}[priority.value]
    return datetime.combine(received, datetime.min.time(), timezone.utc) + timedelta(days=days)


def run_sla_check(db: Session) -> dict:
    now = datetime.now(timezone.utc)
    active = [CaseStatus.PENDING, CaseStatus.UNDER_PROCESS, CaseStatus.TRANSFERRED, CaseStatus.ESCALATED, CaseStatus.REOPENED]
    cases = db.query(Complaint).filter(Complaint.status.in_(active), Complaint.sla_deadline.is_not(None), Complaint.sla_deadline <= now + timedelta(days=3)).all()
    generated = 0
    for case in cases:
        deadline = case.sla_deadline if case.sla_deadline.tzinfo else case.sla_deadline.replace(tzinfo=timezone.utc)
        kind = "overdue" if deadline < now else "deadline"
        recipients = []
        if case.assigned_officer_id:
            recipients.append(case.assigned_officer_id)
        recipients += [u.id for u in db.query(User).filter(User.role.in_([Role.CENTRAL_ADMIN, Role.BUREAU_HEAD]), User.active.is_(True)).all() if u.role == Role.CENTRAL_ADMIN or u.bureau_id == case.assigned_bureau_id]
        window = now.strftime("%Y-%m-%d")
        for recipient in set(recipients):
            if notify(db, recipient, kind, f"SLA {'overdue' if kind == 'overdue' else 'deadline approaching'}", f"{case.complaint_no} requires attention.", "complaint", case.id, f"/complaints/{case.id}", f"sla:{kind}:{case.id}:{recipient}:{window}"):
                generated += 1
    db.commit()
    return {"checked": len(cases), "generated": generated}


