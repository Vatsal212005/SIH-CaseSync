from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import (
    Bureau,
    ComplaintAction,
    CoordinationActionItem,
    CoordinationComplaint,
    CoordinationParticipant,
    CoordinationRecord,
    OverlapFinding,
    RelatedCaseLink,
    Role,
    User,
)
from app.services.audit import audit, notify


def coordinate_finding(
    db: Session,
    finding: OverlapFinding,
    actor: User,
    *,
    owner_id: str | None = None,
    bureau_ids: list[str] | None = None,
    officer_ids: list[str] | None = None,
    next_action: str = "Review the shared evidence and agree the lead bureau response",
    assignee_id: str | None = None,
    due_date: date | None = None,
    remarks: str = "Confirmed overlap requires coordinated bureau action.",
    request_key: str | None = None,
) -> tuple[CoordinationRecord, bool]:
    """Create one auditable coordination workspace for a finding.

    The request key and source finding make retries safe. Existing records are
    returned unchanged rather than duplicated.
    """
    if request_key:
        existing = db.query(CoordinationRecord).filter_by(request_key=request_key).first()
        if existing:
            return existing, False
    existing = db.query(CoordinationRecord).filter_by(source_finding_id=finding.id).first()
    if existing:
        return existing, False

    required_bureaus = {finding.complaint_a.assigned_bureau_id, finding.complaint_b.assigned_bureau_id}
    selected_bureaus = set(bureau_ids or required_bureaus) | required_bureaus
    active_bureaus = {row.id for row in db.query(Bureau).filter(Bureau.id.in_(selected_bureaus), Bureau.active.is_(True)).all()}
    if active_bureaus != selected_bureaus:
        raise HTTPException(422, "All participating bureaus must be active")
    if actor.role == Role.BUREAU_HEAD and actor.bureau_id not in selected_bureaus:
        raise HTTPException(403, "Your bureau must participate in this coordination")

    owner = db.get(User, owner_id or actor.id)
    if not owner or not owner.active or owner.role == Role.AUDITOR:
        raise HTTPException(422, "Coordination owner must be an active authorized official")
    assignee = db.get(User, assignee_id or owner.id)
    if not assignee or not assignee.active or assignee.role == Role.AUDITOR:
        raise HTTPException(422, "Action owner must be an active authorized official")
    if assignee.bureau_id and assignee.bureau_id not in selected_bureaus:
        raise HTTPException(422, "Action owner must belong to a participating bureau")

    selected_officers: dict[str, User] = {}
    for officer_id in officer_ids or []:
        officer = db.get(User, officer_id)
        if not officer or not officer.active or officer.role != Role.CASE_OFFICER or officer.bureau_id not in selected_bureaus:
            raise HTTPException(422, "Responsible officers must be active members of participating bureaus")
        selected_officers[officer.bureau_id] = officer

    target = due_date or date.today() + timedelta(days=14)
    record = CoordinationRecord(
        title=f"Coordination: {finding.complaint_a.complaint_no} / {finding.complaint_b.complaint_no}",
        institution_id=finding.complaint_a.institution_id,
        owner_id=owner.id,
        summary=remarks,
        target_date=target,
        source_finding_id=finding.id,
        request_key=request_key or f"finding:{finding.id}",
    )
    db.add(record)
    db.flush()
    case_ids = sorted([finding.complaint_a_id, finding.complaint_b_id])
    link = db.query(RelatedCaseLink).filter_by(complaint_a_id=case_ids[0], complaint_b_id=case_ids[1]).first()
    if not link:
        db.add(RelatedCaseLink(
            complaint_a_id=case_ids[0], complaint_b_id=case_ids[1],
            relation_type=finding.finding_type, created_by_id=actor.id,
            active=True, justification=remarks,
        ))
    elif not link.active:
        link.active = True
        link.relation_type = finding.finding_type
        link.justification = remarks
    for bureau_id in selected_bureaus:
        db.add(CoordinationParticipant(
            coordination_id=record.id,
            bureau_id=bureau_id,
            user_id=selected_officers.get(bureau_id).id if bureau_id in selected_officers else None,
        ))
    for complaint in (finding.complaint_a, finding.complaint_b):
        db.add(CoordinationComplaint(coordination_id=record.id, complaint_id=complaint.id))
        db.add(ComplaintAction(
            complaint_id=complaint.id,
            actor_id=actor.id,
            action_type="coordination_started",
            from_status=complaint.status.value,
            to_status=complaint.status.value,
            from_bureau_id=complaint.assigned_bureau_id,
            to_bureau_id=complaint.assigned_bureau_id,
            remarks=remarks,
            metadata_json={"coordination_id": record.id, "finding_id": finding.id},
        ))
    item = CoordinationActionItem(
        coordination_id=record.id,
        title=next_action,
        assignee_id=assignee.id,
        due_date=target,
    )
    db.add(item)
    db.flush()
    recipients = {owner.id, assignee.id, *[officer.id for officer in selected_officers.values()]}
    for recipient in recipients:
        notify(
            db,
            recipient,
            "coordination",
            "Cross-bureau coordination created",
            next_action,
            "coordination",
            record.id,
            f"/coordination/{record.id}",
            f"coordination:{record.id}:{recipient}",
        )
    audit(
        db,
        actor.id,
        "coordination.created_from_overlap",
        "coordination",
        record.id,
        after={
            "finding_id": finding.id,
            "complaint_ids": [finding.complaint_a_id, finding.complaint_b_id],
            "bureau_ids": sorted(selected_bureaus),
            "owner_id": owner.id,
            "action_item_id": item.id,
        },
    )
    return record, True
