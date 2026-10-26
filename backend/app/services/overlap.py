import hashlib

from sqlalchemy.orm import Session

from app.ml.engine import embed, score_pair
from app.models import CaseStatus, Complaint, ComplaintEmbedding, OverlapFinding, Role, User
from app.services.audit import notify

ACTIVE = {CaseStatus.PENDING, CaseStatus.UNDER_PROCESS, CaseStatus.TRANSFERRED, CaseStatus.ESCALATED, CaseStatus.REOPENED}


def _fingerprint(a_id: str, b_id: str, text_hashes: list[str]) -> str:
    ids = sorted([a_id, b_id])
    return hashlib.sha256("|".join(ids + sorted(text_hashes)).encode()).hexdigest()


def ensure_embedding(db: Session, complaint: Complaint) -> ComplaintEmbedding:
    text = f"{complaint.title}. {complaint.description}"
    text_hash = hashlib.sha256(text.encode()).hexdigest()
    row = db.get(ComplaintEmbedding, complaint.id)
    if row and row.text_hash == text_hash:
        return row
    vector, backend = embed(text)
    if not row:
        row = ComplaintEmbedding(complaint_id=complaint.id, model_name=backend, vector=vector, text_hash=text_hash)
    else:
        row.model_name, row.vector, row.text_hash = backend, vector, text_hash
    db.add(row)
    db.flush()
    return row


def detect_overlaps(db: Session, complaint: Complaint) -> list[OverlapFinding]:
    if complaint.status not in ACTIVE:
        return []
    emb = ensure_embedding(db, complaint)
    candidates = db.query(Complaint).filter(Complaint.id != complaint.id, Complaint.institution_id == complaint.institution_id, Complaint.status.in_(ACTIVE)).order_by(Complaint.updated_at.desc()).limit(75).all()
    findings = []
    for other in candidates:
        other_emb = ensure_embedding(db, other)
        result = score_pair(complaint, other, emb.vector, other_emb.vector)
        if result["finding_type"] == "unrelated" or result["hybrid"] < 0.42:
            continue
        fingerprint = _fingerprint(complaint.id, other.id, [emb.text_hash, other_emb.text_hash])
        previous = db.query(OverlapFinding).filter(OverlapFinding.fingerprint == fingerprint).first()
        if previous:
            findings.append(previous)
            continue
        finding = OverlapFinding(
            complaint_a_id=complaint.id, complaint_b_id=other.id, finding_type=result["finding_type"],
            similarity_score=result["semantic"], hybrid_score=result["hybrid"], severity=result["severity"], reasons=result["reasons"],
            recommendation="Review the complaints side by side and coordinate bureau action; this is an advisory finding, not an administrative decision.", fingerprint=fingerprint,
        )
        db.add(finding)
        db.flush()
        findings.append(finding)
        recipients = db.query(User).filter(User.active.is_(True), User.role.in_([Role.CENTRAL_ADMIN, Role.BUREAU_HEAD])).all()
        for user in recipients:
            if user.role == Role.CENTRAL_ADMIN or user.bureau_id in {complaint.assigned_bureau_id, other.assigned_bureau_id}:
                notify(db, user.id, "overlap", "Overlap finding requires review", f"{complaint.complaint_no} may relate to {other.complaint_no}.", "overlap", finding.id, f"/overlaps/{finding.id}", f"overlap:{finding.id}:{user.id}")
    return findings

