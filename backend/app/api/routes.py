import csv
import hashlib
import io
import re
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    COOKIE_NAME,
    CSRF_COOKIE,
    can_mutate_case,
    can_view_all,
    create_token,
    get_current_user,
    hash_password,
    new_csrf,
    require_roles,
    verify_csrf,
    verify_password,
)
from app.ml.engine import MODEL_STATUS, normalize_name
from app.models import *
from app.schemas import *
from app.services.audit import audit, notify
from app.services.overlap import detect_overlaps
from app.services.sla import deadline_for, run_sla_check
from app.services.workflow import perform_action

router = APIRouter()


def iso(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value.value if hasattr(value, "value") else value


def aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def institution_dict(row: Institution, counts=None):
    data = {c.name: iso(getattr(row, c.name)) for c in row.__table__.columns}
    data["aliases"] = [x.alias for x in row.aliases]
    if counts:
        data.update(counts)
    return data


def complaint_dict(row: Complaint, detail=False):
    data = {c.name: iso(getattr(row, c.name)) for c in row.__table__.columns}
    data.update(institution={"id": row.institution.id, "permanent_id": row.institution.permanent_id, "name": row.institution.name, "state": row.institution.state, "region": row.institution.region}, category=row.category.name, assigned_bureau={"id": row.assigned_bureau.id, "code": row.assigned_bureau.code, "name": row.assigned_bureau.name}, assigned_officer=({"id": row.assigned_officer.id, "name": row.assigned_officer.full_name} if row.assigned_officer else None))
    if detail:
        data["actions"] = [{"id": a.id, "type": a.action_type, "remarks": a.remarks, "from_status": a.from_status, "to_status": a.to_status, "created_at": iso(a.created_at), "actor": a.actor.full_name} for a in sorted(row.actions, key=lambda x: x.created_at, reverse=True)]
    return data


def scoped(query, user: User):
    if can_view_all(user):
        return query
    return query.filter(Complaint.assigned_bureau_id == user.bureau_id)


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(__import__("sqlalchemy").text("SELECT 1"))
    return {"status": "ok", "database": "connected", "ai": MODEL_STATUS, "synthetic_demo_mode": settings.demo_mode}


@router.post("/auth/login", response_model=UserOut)
def login(payload: LoginInput, response: Response, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    now = datetime.now(timezone.utc)
    if user and user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(429, "Account temporarily locked after failed sign-in attempts")
    if not user or not verify_password(payload.password, user.password_hash):
        if user:
            user.failed_logins += 1
            if user.failed_logins >= 5:
                user.locked_until = now + timedelta(minutes=15)
            db.commit()
        raise HTTPException(401, "Invalid email or password")
    if not user.active:
        raise HTTPException(403, "Account is inactive")
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, now
    audit(db, user.id, "auth.login", "user", user.id, ip=request.client.host if request.client else None)
    db.commit()
    csrf = new_csrf()
    response.set_cookie(COOKIE_NAME, create_token(user), httponly=True, secure=settings.environment == "production", samesite="lax", max_age=settings.access_token_minutes * 60)
    response.set_cookie(CSRF_COOKIE, csrf, httponly=False, secure=settings.environment == "production", samesite="lax", max_age=settings.access_token_minutes * 60)
    return user


@router.post("/auth/logout", dependencies=[Depends(verify_csrf)])
def logout(response: Response, user: User = Depends(get_current_user)):
    response.delete_cookie(COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE)
    return {"ok": True}


@router.get("/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/auth/change-password", dependencies=[Depends(verify_csrf)])
def change_password(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    current, new = payload.get("current_password", ""), payload.get("new_password", "")
    if not verify_password(current, user.password_hash) or len(new) < 10:
        raise HTTPException(422, "Current password or new password policy is invalid")
    user.password_hash = hash_password(new)
    audit(db, user.id, "auth.password_changed", "user", user.id)
    db.commit()
    return {"ok": True}


@router.get("/meta")
def meta(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return {"bureaus": [{"id": x.id, "code": x.code, "name": x.name} for x in db.query(Bureau).filter(Bureau.active.is_(True)).all()], "categories": [{"id": x.id, "name": x.name} for x in db.query(ComplaintCategory).filter(ComplaintCategory.active.is_(True)).all()], "officers": [{"id": x.id, "name": x.full_name, "bureau_id": x.bureau_id} for x in db.query(User).filter(User.active.is_(True), User.role == Role.CASE_OFFICER).all()], "roles": [r.value for r in Role], "demo": settings.demo_mode}


@router.get("/dashboard")
def dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    base = scoped(db.query(Complaint), user)
    now = datetime.now(timezone.utc)
    total = base.count()
    by_status = {s.value: base.filter(Complaint.status == s).count() for s in CaseStatus}
    overdue = base.filter(Complaint.status != CaseStatus.DISPOSED, Complaint.sla_deadline < now).count()
    approaching = base.filter(Complaint.status != CaseStatus.DISPOSED, Complaint.sla_deadline >= now, Complaint.sla_deadline <= now + timedelta(days=3)).count()
    inst = base.filter(Complaint.status != CaseStatus.DISPOSED).with_entities(func.count(func.distinct(Complaint.institution_id))).scalar() or 0
    overlaps = db.query(OverlapFinding).filter(OverlapFinding.review_state == ReviewState.PENDING).count()
    category_rows = scoped(db.query(ComplaintCategory.name, func.count(Complaint.id)).join(Complaint, Complaint.category_id == ComplaintCategory.id), user).group_by(ComplaintCategory.name).all()
    bureau_rows = scoped(db.query(Bureau.code, func.count(Complaint.id)).join(Complaint, Complaint.assigned_bureau_id == Bureau.id), user).group_by(Bureau.code).all()
    month_expr = func.strftime("%Y-%m", Complaint.created_at) if settings.database_url.startswith("sqlite") else func.to_char(Complaint.created_at, "YYYY-MM")
    month_rows = scoped(db.query(month_expr.label("month"), func.count(Complaint.id)), user).group_by(month_expr).order_by(month_expr).all()
    urgent = base.options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)).filter(Complaint.status != CaseStatus.DISPOSED).order_by(Complaint.sla_deadline.asc()).limit(8).all()
    return {"kpis": {"total": total, **by_status, "overdue": overdue, "approaching": approaching, "overlaps": overlaps, "active_institutions": inst}, "category_distribution": [{"name": n, "value": c} for n, c in category_rows], "bureau_workload": [{"name": n, "value": c} for n, c in bureau_rows], "monthly": [{"month": str(m), "value": c} for m, c in month_rows[-12:]], "urgent": [complaint_dict(x) for x in urgent], "synthetic": settings.demo_mode}


@router.get("/institutions")
def institutions(q: str = "", state: str = "", region: str = "", institution_type: str = "", approval_status: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    query = db.query(Institution)
    if q:
        term = f"%{q.strip()}%"
        query = query.filter(or_(Institution.name.ilike(term), Institution.permanent_id.ilike(term), Institution.city.ilike(term)))
    for value, column in [(state, Institution.state), (region, Institution.region), (institution_type, Institution.institution_type), (approval_status, Institution.approval_status)]:
        if value:
            query = query.filter(column == value)
    total = query.count()
    rows = query.order_by(Institution.name).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [institution_dict(x) for x in rows], "total": total, "page": page, "page_size": page_size}


@router.get("/institutions/{institution_id}")
def institution_detail(institution_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(Institution, institution_id)
    if not item:
        raise HTTPException(404, "Institution not found")
    query = scoped(db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)), user).filter(Complaint.institution_id == institution_id)
    complaints = query.order_by(Complaint.created_at.desc()).all()
    now = datetime.now(timezone.utc)
    counts = {"total_complaints": len(complaints), "active_cases": sum(c.status != CaseStatus.DISPOSED for c in complaints), "disposed_cases": sum(c.status == CaseStatus.DISPOSED for c in complaints), "overdue_cases": sum(c.status != CaseStatus.DISPOSED and c.sla_deadline and c.sla_deadline < now for c in complaints), "involved_bureaus": sorted({c.assigned_bureau.code for c in complaints})}
    return {**institution_dict(item, counts), "complaints": [complaint_dict(x) for x in complaints]}


@router.post("/institutions", dependencies=[Depends(verify_csrf)])
def create_institution(payload: InstitutionInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN)), db: Session = Depends(get_db)):
    normalized = normalize_name(payload.name)
    if db.query(Institution).filter(or_(Institution.permanent_id == payload.permanent_id, Institution.normalized_name == normalized)).first():
        raise HTTPException(409, "Institution ID or normalized name already exists")
    data = payload.model_dump(exclude={"aliases"})
    item = Institution(**data, normalized_name=normalized)
    db.add(item); db.flush()
    for alias in payload.aliases:
        db.add(InstitutionAlias(institution_id=item.id, alias=alias, normalized_alias=normalize_name(alias)))
    audit(db, user.id, "institution.created", "institution", item.id, after={"permanent_id": item.permanent_id, "name": item.name})
    db.commit(); db.refresh(item)
    return institution_dict(item)


@router.put("/institutions/{institution_id}", dependencies=[Depends(verify_csrf)])
def update_institution(institution_id: str, payload: InstitutionInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN)), db: Session = Depends(get_db)):
    item = db.get(Institution, institution_id)
    if not item: raise HTTPException(404, "Institution not found")
    before = {"name": item.name, "permanent_id": item.permanent_id}
    for k, v in payload.model_dump(exclude={"aliases"}).items(): setattr(item, k, v)
    item.normalized_name = normalize_name(item.name)
    item.aliases.clear()
    for alias in payload.aliases: item.aliases.append(InstitutionAlias(alias=alias, normalized_alias=normalize_name(alias)))
    audit(db, user.id, "institution.updated", "institution", item.id, before, {"name": item.name, "permanent_id": item.permanent_id})
    try: db.commit()
    except IntegrityError as exc: db.rollback(); raise HTTPException(409, "Institution identity conflicts with an existing record") from exc
    return institution_dict(item)


@router.post("/institutions/import", dependencies=[Depends(verify_csrf)])
async def import_institutions(file: UploadFile = File(...), user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN)), db: Session = Depends(get_db)):
    if not file.filename or not file.filename.lower().endswith(".csv"): raise HTTPException(415, "A CSV file is required")
    content = (await file.read()).decode("utf-8-sig")
    required = {"permanent_id", "name", "address", "city", "state", "region", "postal_code", "institution_type", "approval_status"}
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames or not required.issubset(reader.fieldnames): raise HTTPException(422, {"missing_columns": sorted(required - set(reader.fieldnames or []))})
    errors, created = [], 0
    job = ImportJob(kind="institutions", filename=file.filename, status="processing", uploaded_by_id=user.id); db.add(job); db.flush()
    for line, row in enumerate(reader, start=2):
        try:
            with db.begin_nested():
                if not re.fullmatch(r"[0-9]{6}", row["postal_code"]): raise ValueError("postal_code must contain six digits")
                normalized = normalize_name(row["name"])
                if db.query(Institution).filter(or_(Institution.permanent_id == row["permanent_id"], Institution.normalized_name == normalized)).first(): raise ValueError("duplicate institution identity")
                db.add(Institution(**{k: row[k] for k in required}, normalized_name=normalized, contact_email=row.get("contact_email") or None, is_synthetic=False)); db.flush()
            created += 1
        except Exception as exc:
            errors.append({"line": line, "error": str(exc)[:200]})
    job.status, job.created_count, job.error_count, job.errors = "completed_with_errors" if errors else "completed", created, len(errors), errors[:200]
    audit(db, user.id, "import.institutions", "import_job", job.id, after={"created": created, "errors": len(errors)})
    db.commit()
    return {"job_id": job.id, "created": created, "errors": errors}


@router.get("/complaints")
def complaints(q: str = "", status: str = "", priority: str = "", bureau_id: str = "", institution_id: str = "", category_id: str = "", date_from: date | None = None, date_to: date | None = None, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), sort: str = "-created_at", user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = scoped(db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)), user)
    if q:
        term = f"%{q.strip()}%"; query = query.join(Institution).filter(or_(Complaint.complaint_no.ilike(term), Complaint.title.ilike(term), Complaint.description.ilike(term), Institution.name.ilike(term), Institution.permanent_id.ilike(term)))
    filters = [(status, Complaint.status), (priority, Complaint.priority), (bureau_id, Complaint.assigned_bureau_id), (institution_id, Complaint.institution_id), (category_id, Complaint.category_id)]
    for value, column in filters:
        if value: query = query.filter(column == value)
    if date_from: query = query.filter(Complaint.date_received >= date_from)
    if date_to: query = query.filter(Complaint.date_received <= date_to)
    total = query.count(); order = Complaint.created_at.asc() if sort == "created_at" else Complaint.created_at.desc()
    rows = query.order_by(order).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [complaint_dict(x) for x in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/complaints", dependencies=[Depends(verify_csrf)])
def create_complaint(payload: ComplaintInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD, Role.CASE_OFFICER)), db: Session = Depends(get_db)):
    if not db.get(Institution, payload.institution_id) or not db.get(Bureau, payload.assigned_bureau_id) or not db.get(ComplaintCategory, payload.category_id): raise HTTPException(422, "Institution, bureau or category is invalid")
    if user.role in {Role.BUREAU_HEAD, Role.CASE_OFFICER} and user.bureau_id != payload.assigned_bureau_id: raise HTTPException(403, "Users may register cases only in their bureau")
    data = payload.model_dump()
    if user.role == Role.CASE_OFFICER:
        data["assigned_officer_id"] = user.id
    elif payload.assigned_officer_id:
        officer = db.get(User, payload.assigned_officer_id)
        if not officer or not officer.active or officer.role != Role.CASE_OFFICER or officer.bureau_id != payload.assigned_bureau_id:
            raise HTTPException(422, "Assigned officer must be active in the assigned bureau")
    seq = (db.query(func.count(Complaint.id)).scalar() or 0) + 1
    number = f"CMP-{date.today().year}-{seq:06d}"
    item = Complaint(**data, complaint_no=number, originating_bureau_id=payload.assigned_bureau_id, status=CaseStatus.PENDING, created_by_id=user.id, is_synthetic=settings.demo_mode)
    item.sla_deadline = deadline_for(db, item.category_id, item.priority, item.assigned_bureau_id, item.date_received)
    db.add(item); db.flush()
    db.add(ComplaintAction(complaint_id=item.id, actor_id=user.id, action_type="registered", to_status=CaseStatus.PENDING.value, to_bureau_id=item.assigned_bureau_id, remarks="Complaint registered"))
    audit(db, user.id, "complaint.created", "complaint", item.id, after={"complaint_no": number})
    detect_overlaps(db, item)
    db.commit()
    item = db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)).filter(Complaint.id == item.id).one()
    return complaint_dict(item, True)


@router.post("/complaints/import", dependencies=[Depends(verify_csrf)])
async def import_complaints(file: UploadFile = File(...), user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN)), db: Session = Depends(get_db)):
    """Validated adapter format for future authorized exports; no government API is assumed."""
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(415, "A CSV file is required")
    required = {"institution_permanent_id", "title", "description", "category", "priority", "source", "stakeholder_type", "date_received", "bureau_code"}
    reader = csv.DictReader(io.StringIO((await file.read()).decode("utf-8-sig")))
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise HTTPException(422, {"missing_columns": sorted(required - set(reader.fieldnames or []))})
    errors, created = [], 0
    job = ImportJob(kind="complaints", filename=file.filename, status="processing", uploaded_by_id=user.id)
    db.add(job); db.flush()
    for line, row in enumerate(reader, start=2):
        try:
            with db.begin_nested():
                institution = db.query(Institution).filter_by(permanent_id=row["institution_permanent_id"]).one_or_none()
                category = db.query(ComplaintCategory).filter(func.lower(ComplaintCategory.name) == row["category"].lower()).one_or_none()
                bureau = db.query(Bureau).filter(func.lower(Bureau.code) == row["bureau_code"].lower()).one_or_none()
                if not institution or not category or not bureau:
                    raise ValueError("institution_permanent_id, category or bureau_code could not be resolved")
                priority = Priority(row["priority"].lower())
                received = date.fromisoformat(row["date_received"])
                if len(row["description"].strip()) < 20:
                    raise ValueError("description must contain at least 20 characters")
                seq = (db.query(func.count(Complaint.id)).scalar() or 0) + 1
                item = Complaint(complaint_no=f"CMP-{date.today().year}-{seq:06d}", institution_id=institution.id, title=row["title"][:300], description=row["description"], category_id=category.id, priority=priority, source=row["source"][:80], stakeholder_type=row["stakeholder_type"][:80], date_received=received, originating_bureau_id=bureau.id, assigned_bureau_id=bureau.id, status=CaseStatus.PENDING, created_by_id=user.id, is_synthetic=False)
                item.sla_deadline = deadline_for(db, category.id, priority, bureau.id, received)
                db.add(item); db.flush(); db.add(ComplaintAction(complaint_id=item.id, actor_id=user.id, action_type="imported", to_status="pending", to_bureau_id=bureau.id, remarks=f"Imported via validated CSV job {job.id}")); detect_overlaps(db, item)
            created += 1
        except Exception as exc:
            errors.append({"line": line, "error": str(exc)[:200]})
    job.status = "completed_with_errors" if errors else "completed"; job.created_count = created; job.error_count = len(errors); job.errors = errors[:200]
    audit(db, user.id, "import.complaints", "import_job", job.id, after={"created": created, "errors": len(errors)})
    db.commit()
    return {"job_id": job.id, "created": created, "errors": errors}


@router.get("/complaints/{complaint_id}")
def complaint_detail(complaint_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = scoped(db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer), joinedload(Complaint.actions).joinedload(ComplaintAction.actor)), user).filter(Complaint.id == complaint_id).first()
    if not item: raise HTTPException(404, "Complaint not found")
    data = complaint_dict(item, True)
    data["attachments"] = [{c.name: iso(getattr(x, c.name)) for c in x.__table__.columns if c.name != "stored_name"} for x in db.query(ComplaintAttachment).filter_by(complaint_id=item.id).all()]
    findings = db.query(OverlapFinding).filter(or_(OverlapFinding.complaint_a_id == item.id, OverlapFinding.complaint_b_id == item.id)).all()
    data["overlaps"] = [finding_dict(x) for x in findings]
    data["related_cases"] = [{c.name: iso(getattr(x, c.name)) for c in x.__table__.columns} for x in db.query(RelatedCaseLink).filter(or_(RelatedCaseLink.complaint_a_id == item.id, RelatedCaseLink.complaint_b_id == item.id), RelatedCaseLink.active.is_(True)).all()]
    return data


@router.put("/complaints/{complaint_id}", dependencies=[Depends(verify_csrf)])
def update_complaint(complaint_id: str, payload: ComplaintEditInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Complaint, complaint_id)
    if not item: raise HTTPException(404, "Complaint not found")
    if not can_mutate_case(user, item): raise HTTPException(403, "You cannot edit this complaint")
    if item.status == CaseStatus.DISPOSED: raise HTTPException(409, "Reopen a disposed complaint before editing it")
    if not db.get(ComplaintCategory, payload.category_id): raise HTTPException(422, "Complaint category is invalid")
    before = {"title": item.title, "description": item.description, "category_id": item.category_id, "priority": item.priority.value, "next_action": item.next_action}
    for key, value in payload.model_dump().items(): setattr(item, key, value)
    item.sla_deadline = deadline_for(db, item.category_id, item.priority, item.assigned_bureau_id, item.date_received)
    item.version += 1; item.updated_at = datetime.now(timezone.utc)
    db.add(ComplaintAction(complaint_id=item.id, actor_id=user.id, action_type="edited", from_status=item.status.value, to_status=item.status.value, from_bureau_id=item.assigned_bureau_id, to_bureau_id=item.assigned_bureau_id, remarks="Permitted complaint fields updated"))
    audit(db, user.id, "complaint.updated", "complaint", item.id, before, payload.model_dump(mode="json"))
    detect_overlaps(db, item); db.commit()
    return {"id": item.id, "version": item.version}


@router.post("/complaints/{complaint_id}/links", dependencies=[Depends(verify_csrf)])
def link_complaint(complaint_id: str, payload: LinkInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD)), db: Session = Depends(get_db)):
    first, second = db.get(Complaint, complaint_id), db.get(Complaint, payload.other_complaint_id)
    if not first or not second or first.id == second.id: raise HTTPException(422, "Two different valid complaints are required")
    if user.role == Role.BUREAU_HEAD and user.bureau_id not in {first.assigned_bureau_id, second.assigned_bureau_id}:
        raise HTTPException(403, "Neither complaint belongs to your bureau")
    ids = sorted([first.id, second.id]); existing = db.query(RelatedCaseLink).filter_by(complaint_a_id=ids[0], complaint_b_id=ids[1]).first()
    if existing and existing.active: raise HTTPException(409, "Cases are already linked")
    if existing:
        existing.active = True; existing.relation_type = payload.relation_type; existing.justification = payload.justification; existing.created_by_id = user.id
        link = existing
    else:
        link = RelatedCaseLink(complaint_a_id=ids[0], complaint_b_id=ids[1], relation_type=payload.relation_type, justification=payload.justification, created_by_id=user.id); db.add(link)
    db.flush()
    audit(db, user.id, "complaint.linked", "related_case_link", link.id, after={"complaints": ids, "relation": payload.relation_type}); db.commit()
    return {"id": link.id, "active": True}


@router.delete("/complaints/{complaint_id}/links/{link_id}", dependencies=[Depends(verify_csrf)])
def unlink_complaint(complaint_id: str, link_id: str, justification: str = Query(min_length=3, max_length=5000), user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD)), db: Session = Depends(get_db)):
    link = db.get(RelatedCaseLink, link_id)
    if not link or complaint_id not in {link.complaint_a_id, link.complaint_b_id}: raise HTTPException(404, "Related case link not found")
    if user.role == Role.BUREAU_HEAD:
        first, second = db.get(Complaint, link.complaint_a_id), db.get(Complaint, link.complaint_b_id)
        if user.bureau_id not in {first.assigned_bureau_id, second.assigned_bureau_id}:
            raise HTTPException(403, "Neither complaint belongs to your bureau")
    link.active = False; audit(db, user.id, "complaint.unlinked", "related_case_link", link.id, before={"active": True}, after={"active": False, "justification": justification}); db.commit()
    return {"id": link.id, "active": False}


@router.post("/complaints/{complaint_id}/actions", dependencies=[Depends(verify_csrf)])
def complaint_action(complaint_id: str, payload: ActionInput, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(Complaint, complaint_id)
    if not item: raise HTTPException(404, "Complaint not found")
    if not can_mutate_case(user, item): raise HTTPException(403, "You cannot modify this complaint")
    perform_action(db, item, user, payload)
    if payload.action in {"start", "accept_transfer", "reopen"}: detect_overlaps(db, item)
    db.commit()
    return {"id": item.id, "status": item.status.value, "assigned_bureau_id": item.assigned_bureau_id, "assigned_officer_id": item.assigned_officer_id, "version": item.version}


@router.post("/complaints/{complaint_id}/attachments", dependencies=[Depends(verify_csrf)])
async def upload_attachment(complaint_id: str, file: UploadFile = File(...), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    complaint = db.get(Complaint, complaint_id)
    if not complaint or not can_mutate_case(user, complaint): raise HTTPException(403, "Attachment access denied")
    allowed = {"application/pdf", "image/png", "image/jpeg", "text/plain", "text/csv"}
    if file.content_type not in allowed: raise HTTPException(415, "Unsupported file type")
    content = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
    if len(content) > settings.max_upload_mb * 1024 * 1024: raise HTTPException(413, "File is too large")
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored = f"{uuid.uuid4().hex}{Path(file.filename or '').suffix.lower()}"
    (settings.upload_dir / stored).write_bytes(content)
    row = ComplaintAttachment(complaint_id=complaint.id, original_name=Path(file.filename or "attachment").name, stored_name=stored, content_type=file.content_type, size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest(), uploaded_by_id=user.id)
    db.add(row); audit(db, user.id, "attachment.uploaded", "complaint", complaint.id, after={"attachment_id": row.id, "size": len(content)}); db.commit()
    return {"id": row.id, "name": row.original_name, "size": row.size_bytes}


@router.get("/attachments/{attachment_id}")
def download_attachment(attachment_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(ComplaintAttachment, attachment_id)
    if not row: raise HTTPException(404, "Attachment not found")
    complaint = db.get(Complaint, row.complaint_id)
    if not can_view_all(user) and complaint.assigned_bureau_id != user.bureau_id: raise HTTPException(403, "Attachment access denied")
    path = settings.upload_dir / row.stored_name
    if not path.is_file(): raise HTTPException(404, "Attachment data is unavailable")
    return FileResponse(path, media_type=row.content_type, filename=row.original_name)


def finding_dict(x: OverlapFinding):
    return {"id": x.id, "complaint_a": complaint_dict(x.complaint_a), "complaint_b": complaint_dict(x.complaint_b), "finding_type": x.finding_type, "similarity_score": x.similarity_score, "hybrid_score": x.hybrid_score, "severity": x.severity, "reasons": x.reasons, "recommendation": x.recommendation, "review_state": x.review_state.value, "reviewer_id": x.reviewer_id, "resolution_notes": x.resolution_notes, "detected_at": iso(x.detected_at)}


@router.get("/overlaps")
def overlaps(state: str = "", severity: str = "", page: int = 1, page_size: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(OverlapFinding).options(joinedload(OverlapFinding.complaint_a).joinedload(Complaint.institution), joinedload(OverlapFinding.complaint_a).joinedload(Complaint.category), joinedload(OverlapFinding.complaint_a).joinedload(Complaint.assigned_bureau), joinedload(OverlapFinding.complaint_a).joinedload(Complaint.assigned_officer), joinedload(OverlapFinding.complaint_b).joinedload(Complaint.institution), joinedload(OverlapFinding.complaint_b).joinedload(Complaint.category), joinedload(OverlapFinding.complaint_b).joinedload(Complaint.assigned_bureau), joinedload(OverlapFinding.complaint_b).joinedload(Complaint.assigned_officer))
    if not can_view_all(user): query = query.join(Complaint, Complaint.id == OverlapFinding.complaint_a_id).filter(or_(Complaint.assigned_bureau_id == user.bureau_id, OverlapFinding.complaint_b_id.in_(db.query(Complaint.id).filter(Complaint.assigned_bureau_id == user.bureau_id))))
    if state: query = query.filter(OverlapFinding.review_state == state)
    if severity: query = query.filter(OverlapFinding.severity == severity)
    total = query.count(); rows = query.order_by(OverlapFinding.detected_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [finding_dict(x) for x in rows], "total": total}


@router.get("/overlaps/{finding_id}")
def overlap_detail(finding_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(OverlapFinding, finding_id)
    if not row: raise HTTPException(404, "Finding not found")
    if not can_view_all(user) and user.bureau_id not in {row.complaint_a.assigned_bureau_id, row.complaint_b.assigned_bureau_id}:
        raise HTTPException(403, "Finding is outside your bureau")
    return finding_dict(row)


@router.post("/overlaps/{finding_id}/review", dependencies=[Depends(verify_csrf)])
def review_overlap(finding_id: str, payload: ReviewInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD)), db: Session = Depends(get_db)):
    finding = db.get(OverlapFinding, finding_id)
    if not finding: raise HTTPException(404, "Finding not found")
    if user.role == Role.BUREAU_HEAD and user.bureau_id not in {finding.complaint_a.assigned_bureau_id, finding.complaint_b.assigned_bureau_id}: raise HTTPException(403, "Finding is outside your bureau")
    finding.review_state, finding.reviewer_id, finding.resolution_notes = payload.decision, user.id, payload.notes
    db.add(OverlapReview(finding_id=finding.id, reviewer_id=user.id, decision=payload.decision.value, notes=payload.notes))
    coordination_id = None
    if payload.decision == ReviewState.CONFIRMED:
        ids = sorted([finding.complaint_a_id, finding.complaint_b_id])
        if not db.query(RelatedCaseLink).filter_by(complaint_a_id=ids[0], complaint_b_id=ids[1]).first(): db.add(RelatedCaseLink(complaint_a_id=ids[0], complaint_b_id=ids[1], relation_type=finding.finding_type, created_by_id=user.id, justification=payload.notes))
        if payload.create_coordination:
            record = CoordinationRecord(title=f"Coordination: {finding.complaint_a.complaint_no} / {finding.complaint_b.complaint_no}", institution_id=finding.complaint_a.institution_id, owner_id=user.id, summary=payload.notes, target_date=date.today() + timedelta(days=14))
            db.add(record); db.flush(); coordination_id = record.id
            for bureau_id in {finding.complaint_a.assigned_bureau_id, finding.complaint_b.assigned_bureau_id}: db.add(CoordinationParticipant(coordination_id=record.id, bureau_id=bureau_id))
    audit(db, user.id, "overlap.reviewed", "overlap", finding.id, after={"decision": payload.decision.value, "coordination_id": coordination_id})
    db.commit()
    return {"id": finding.id, "review_state": finding.review_state.value, "coordination_id": coordination_id}


@router.get("/coordination")
def coordination(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(CoordinationRecord, Institution.name, User.full_name).join(Institution, Institution.id == CoordinationRecord.institution_id).join(User, User.id == CoordinationRecord.owner_id)
    if not can_view_all(user):
        query = query.join(CoordinationParticipant, CoordinationParticipant.coordination_id == CoordinationRecord.id).filter(CoordinationParticipant.bureau_id == user.bureau_id)
    rows = query.order_by(CoordinationRecord.updated_at.desc()).all()
    return [{**{c.name: iso(getattr(r, c.name)) for c in r.__table__.columns}, "institution_name": name, "owner_name": owner, "participants": [x.bureau_id for x in db.query(CoordinationParticipant).filter_by(coordination_id=r.id)], "action_items": [{c.name: iso(getattr(x, c.name)) for c in x.__table__.columns} for x in db.query(CoordinationActionItem).filter_by(coordination_id=r.id)]} for r, name, owner in rows]


@router.post("/coordination", dependencies=[Depends(verify_csrf)])
def create_coordination(payload: CoordinationInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD)), db: Session = Depends(get_db)):
    if user.role == Role.BUREAU_HEAD and user.bureau_id not in payload.bureau_ids:
        raise HTTPException(403, "Your bureau must participate in this coordination record")
    record = CoordinationRecord(**payload.model_dump(exclude={"bureau_ids", "complaint_ids"})); db.add(record); db.flush()
    for bureau_id in set(payload.bureau_ids): db.add(CoordinationParticipant(coordination_id=record.id, bureau_id=bureau_id))
    for case_id in payload.complaint_ids:
        complaint = db.get(Complaint, case_id)
        if not complaint or complaint.institution_id != payload.institution_id: raise HTTPException(422, "All complaints must belong to the coordination institution")
    audit(db, user.id, "coordination.created", "coordination", record.id); db.commit()
    return {"id": record.id}


@router.post("/coordination/{coordination_id}/actions", dependencies=[Depends(verify_csrf)])
def coordination_action(coordination_id: str, payload: ActionItemInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.BUREAU_HEAD)), db: Session = Depends(get_db)):
    if not db.get(CoordinationRecord, coordination_id): raise HTTPException(404, "Coordination record not found")
    if user.role == Role.BUREAU_HEAD and not db.query(CoordinationParticipant).filter_by(coordination_id=coordination_id, bureau_id=user.bureau_id).first():
        raise HTTPException(403, "Coordination record is outside your bureau")
    item = CoordinationActionItem(coordination_id=coordination_id, **payload.model_dump()); db.add(item)
    notify(db, payload.assignee_id, "coordination", "Coordination action assigned", payload.title, "coordination", coordination_id, f"/coordination/{coordination_id}")
    db.commit(); return {"id": item.id}


@router.patch("/coordination/actions/{item_id}", dependencies=[Depends(verify_csrf)])
def complete_action(item_id: str, payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.get(CoordinationActionItem, item_id)
    if not item or (item.assignee_id != user.id and user.role not in {Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN}): raise HTTPException(403, "Action item access denied")
    item.completed = bool(payload.get("completed", True)); item.completed_at = datetime.now(timezone.utc) if item.completed else None; db.commit()
    return {"id": item.id, "completed": item.completed}


@router.get("/notifications")
def notifications(unread_only: bool = False, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.recipient_id == user.id)
    if unread_only: query = query.filter(Notification.read_at.is_(None))
    rows = query.order_by(Notification.created_at.desc()).limit(100).all()
    return {"items": [{c.name: iso(getattr(x, c.name)) for c in x.__table__.columns} for x in rows], "unread": db.query(Notification).filter(Notification.recipient_id == user.id, Notification.read_at.is_(None)).count()}


@router.post("/notifications/read", dependencies=[Depends(verify_csrf)])
def mark_notifications(payload: dict, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    query = db.query(Notification).filter(Notification.recipient_id == user.id, Notification.read_at.is_(None))
    if payload.get("ids"): query = query.filter(Notification.id.in_(payload["ids"]))
    count = query.update({Notification.read_at: datetime.now(timezone.utc)}, synchronize_session=False); db.commit(); return {"updated": count}


@router.get("/search")
def global_search(q: str = Query(min_length=2), user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    term = f"%{q.strip()}%"
    inst = db.query(Institution).filter(or_(Institution.name.ilike(term), Institution.permanent_id.ilike(term))).limit(8).all()
    cases = scoped(db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)).join(Institution), user).filter(or_(Complaint.complaint_no.ilike(term), Complaint.title.ilike(term), Complaint.description.ilike(term), Institution.name.ilike(term))).limit(12).all()
    return {"institutions": [institution_dict(x) for x in inst], "complaints": [complaint_dict(x) for x in cases]}


def report_query(db, user, bureau_id="", region="", status="", category_id="", date_from=None, date_to=None):
    q = scoped(db.query(Complaint).options(joinedload(Complaint.institution), joinedload(Complaint.category), joinedload(Complaint.assigned_bureau), joinedload(Complaint.assigned_officer)).join(Institution), user)
    if bureau_id: q = q.filter(Complaint.assigned_bureau_id == bureau_id)
    if region: q = q.filter(Institution.region == region)
    if status: q = q.filter(Complaint.status == status)
    if category_id: q = q.filter(Complaint.category_id == category_id)
    if date_from: q = q.filter(Complaint.date_received >= date_from)
    if date_to: q = q.filter(Complaint.date_received <= date_to)
    return q


REPORT_TYPES = {
    "institution_history", "bureau_workload", "region_statistics", "state_distribution",
    "pending_ageing", "disposal_rate", "sla_compliance", "overlap_cases",
    "officer_workload", "monthly_performance", "quarterly_performance", "transfer_escalation",
}


def aggregate_report(rows: list[Complaint], db: Session, report_type: str) -> list[dict]:
    def grouped(key, label):
        values = sorted({key(x) for x in rows if key(x)})
        return [{label: value, "total": sum(key(x) == value for x in rows), "active": sum(key(x) == value and x.status != CaseStatus.DISPOSED for x in rows), "disposed": sum(key(x) == value and x.status == CaseStatus.DISPOSED for x in rows)} for value in values]
    if report_type == "institution_history": return grouped(lambda x: x.institution.name, "institution")
    if report_type == "bureau_workload": return grouped(lambda x: x.assigned_bureau.code, "bureau")
    if report_type == "region_statistics": return grouped(lambda x: x.institution.region, "region")
    if report_type == "state_distribution": return grouped(lambda x: x.institution.state, "state")
    if report_type == "officer_workload": return grouped(lambda x: x.assigned_officer.full_name if x.assigned_officer else "Unassigned", "officer")
    if report_type in {"monthly_performance", "quarterly_performance"}:
        key = (lambda x: f"{x.date_received.year}-{x.date_received.month:02d}") if report_type == "monthly_performance" else (lambda x: f"{x.date_received.year}-Q{((x.date_received.month-1)//3)+1}")
        return grouped(key, "period")
    if report_type == "pending_ageing":
        today = date.today(); buckets = [("0-7 days",0,7),("8-30 days",8,30),("31-60 days",31,60),("61+ days",61,99999)]
        return [{"age_band": label, "cases": sum(x.status != CaseStatus.DISPOSED and lo <= (today-x.date_received).days <= hi for x in rows)} for label,lo,hi in buckets]
    if report_type in {"disposal_rate", "sla_compliance"}:
        result = grouped(lambda x: x.assigned_bureau.code, "bureau")
        for item in result:
            scoped_rows = [x for x in rows if x.assigned_bureau.code == item["bureau"]]
            if report_type == "disposal_rate": item["rate_percent"] = round(100*item["disposed"]/max(1,item["total"]),1)
            else:
                disposed = [x for x in scoped_rows if x.status == CaseStatus.DISPOSED and x.disposal_date and x.sla_deadline]
                compliant = sum(datetime.combine(x.disposal_date, datetime.min.time(), timezone.utc) <= aware(x.sla_deadline) for x in disposed)
                item["rate_percent"] = round(100*compliant/max(1,len(disposed)),1)
        return result
    if report_type == "overlap_cases":
        findings = db.query(OverlapFinding).all(); kinds = sorted({x.finding_type for x in findings})
        return [{"finding_type": kind.replace("_", " "), "count": sum(x.finding_type == kind for x in findings), "pending_review": sum(x.finding_type == kind and x.review_state == ReviewState.PENDING for x in findings)} for kind in kinds]
    if report_type == "transfer_escalation":
        case_ids = [x.id for x in rows]; actions = db.query(ComplaintAction).filter(ComplaintAction.complaint_id.in_(case_ids), ComplaintAction.action_type.in_(["transfer", "escalate"])).all() if case_ids else []
        return [{"event": event, "count": sum(x.action_type == event for x in actions)} for event in ["transfer", "escalate"]]
    return []


@router.get("/reports/summary")
def report_summary(report_type: str = "bureau_workload", bureau_id: str = "", region: str = "", status: str = "", category_id: str = "", date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if report_type not in REPORT_TYPES: raise HTTPException(422, "Unsupported report type")
    rows = report_query(db, user, bureau_id, region, status, category_id, date_from, date_to).all(); now = datetime.now(timezone.utc)
    return {"report_type": report_type, "total": len(rows), "disposed": sum(x.status == CaseStatus.DISPOSED for x in rows), "overdue": sum(x.status != CaseStatus.DISPOSED and aware(x.sla_deadline) and aware(x.sla_deadline) < now for x in rows), "sla_compliance_rate": round(100 * sum(x.status == CaseStatus.DISPOSED and x.disposal_date and datetime.combine(x.disposal_date, datetime.min.time(), timezone.utc) <= aware(x.sla_deadline) for x in rows) / max(1, sum(x.status == CaseStatus.DISPOSED for x in rows)), 1), "by_status": [{"name": s.value, "value": sum(x.status == s for x in rows)} for s in CaseStatus], "by_region": [{"name": n, "value": sum(x.institution.region == n for x in rows)} for n in sorted({x.institution.region for x in rows})], "report_rows": aggregate_report(rows, db, report_type), "records": [complaint_dict(x) for x in rows[:100]]}


@router.get("/reports/export.csv")
def export_csv(bureau_id: str = "", region: str = "", status: str = "", category_id: str = "", date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = report_query(db, user, bureau_id, region, status, category_id, date_from, date_to).all(); output = io.StringIO(); writer = csv.writer(output)
    writer.writerow(["Complaint ID", "Institution ID", "Institution", "State", "Region", "Bureau", "Category", "Priority", "Status", "Received", "SLA Deadline", "Synthetic"])
    for x in rows: writer.writerow([x.complaint_no, x.institution.permanent_id, x.institution.name, x.institution.state, x.institution.region, x.assigned_bureau.code, x.category.name, x.priority.value, x.status.value, x.date_received, iso(x.sla_deadline), x.is_synthetic])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=casesync-report.csv"})


@router.get("/reports/export.pdf")
def export_pdf(bureau_id: str = "", region: str = "", status: str = "", category_id: str = "", date_from: date | None = None, date_to: date | None = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = report_query(db, user, bureau_id, region, status, category_id, date_from, date_to).all(); buffer = io.BytesIO(); styles = getSampleStyleSheet(); doc = SimpleDocTemplate(buffer, pagesize=landscape(A4), leftMargin=24, rightMargin=24)
    story = [Paragraph("AICTE CaseSync — Complaint Operations Report", styles["Title"]), Paragraph(f"Generated {datetime.now(timezone.utc).strftime('%d %b %Y %H:%M UTC')} · Synthetic demonstration data: {'Yes' if settings.demo_mode else 'No'}", styles["Normal"]), Paragraph(f"Filters — bureau: {bureau_id or 'All'}, region: {region or 'All'}, status: {status or 'All'}, category: {category_id or 'All'}, range: {date_from or 'Any'} to {date_to or 'Any'}", styles["Normal"]), Spacer(1, 12)]
    data = [["Case", "Institution", "Region", "Bureau", "Category", "Priority", "Status", "Received"]] + [[x.complaint_no, x.institution.name[:28], x.institution.region, x.assigned_bureau.code, x.category.name[:20], x.priority.value, x.status.value, str(x.date_received)] for x in rows[:500]]
    table = Table(data, repeatRows=1, colWidths=[75, 150, 70, 50, 110, 55, 75, 65]); table.setStyle(TableStyle([("BACKGROUND", (0,0), (-1,0), colors.HexColor("#12304A")), ("TEXTCOLOR", (0,0), (-1,0), colors.white), ("FONTSIZE", (0,0), (-1,-1), 7), ("GRID", (0,0), (-1,-1), .25, colors.HexColor("#CBD5E1")), ("VALIGN", (0,0), (-1,-1), "TOP"), ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F8FAFC")])]))
    story += [Paragraph(f"Total records: {len(rows)}", styles["Heading2"]), table]; doc.build(story); buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/pdf", headers={"Content-Disposition": "attachment; filename=casesync-report.pdf"})


@router.get("/audit")
def audit_log(page: int = 1, page_size: int = 30, action: str = "", user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN, Role.AUDITOR)), db: Session = Depends(get_db)):
    query = db.query(AuditEvent, User.full_name).outerjoin(User, User.id == AuditEvent.actor_id)
    if action: query = query.filter(AuditEvent.action.ilike(f"%{action}%"))
    total = query.count(); rows = query.order_by(AuditEvent.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "items": [{**{c.name: iso(getattr(e, c.name)) for c in e.__table__.columns}, "actor_name": name or "System"} for e, name in rows]}


@router.get("/admin/users")
def users(user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    return [{c.name: iso(getattr(x, c.name)) for c in x.__table__.columns if c.name != "password_hash"} for x in db.query(User).order_by(User.full_name).all()]


@router.post("/admin/bureaus", dependencies=[Depends(verify_csrf)])
def create_bureau(payload: BureauInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item = Bureau(**payload.model_dump()); db.add(item)
    try: db.flush()
    except IntegrityError as exc: db.rollback(); raise HTTPException(409, "Bureau code already exists") from exc
    audit(db, user.id, "bureau.created", "bureau", item.id, after=payload.model_dump()); db.commit(); return {"id": item.id}


@router.patch("/admin/bureaus/{bureau_id}", dependencies=[Depends(verify_csrf)])
def update_bureau(bureau_id: str, payload: BureauInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item = db.get(Bureau, bureau_id)
    if not item: raise HTTPException(404, "Bureau not found")
    before = {"code": item.code, "name": item.name, "active": item.active}
    for key,value in payload.model_dump().items(): setattr(item,key,value)
    audit(db,user.id,"bureau.updated","bureau",item.id,before,payload.model_dump()); db.commit(); return {"ok": True}


@router.post("/admin/categories", dependencies=[Depends(verify_csrf)])
def create_category(payload: CategoryInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item = ComplaintCategory(**payload.model_dump()); db.add(item)
    try: db.flush()
    except IntegrityError as exc: db.rollback(); raise HTTPException(409, "Category already exists") from exc
    audit(db,user.id,"category.created","category",item.id,after=payload.model_dump()); db.commit(); return {"id": item.id}


@router.patch("/admin/categories/{category_id}", dependencies=[Depends(verify_csrf)])
def update_category(category_id: str, payload: CategoryInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item=db.get(ComplaintCategory,category_id)
    if not item: raise HTTPException(404,"Category not found")
    before={"name":item.name,"active":item.active}; item.name=payload.name; item.active=payload.active
    audit(db,user.id,"category.updated","category",item.id,before,payload.model_dump()); db.commit(); return {"ok":True}


@router.post("/admin/users", dependencies=[Depends(verify_csrf)])
def create_user(payload: AdminUserInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item = User(**payload.model_dump(exclude={"password"}), password_hash=hash_password(payload.password)); db.add(item)
    try: db.flush()
    except IntegrityError as exc: db.rollback(); raise HTTPException(409, "Email already exists") from exc
    audit(db, user.id, "user.created", "user", item.id, after={"email": item.email, "role": item.role.value}); db.commit(); return {"id": item.id}


@router.patch("/admin/users/{user_id}", dependencies=[Depends(verify_csrf)])
def update_user(user_id: str, payload: dict, actor: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    item = db.get(User, user_id)
    if not item: raise HTTPException(404, "User not found")
    for field in ["active", "bureau_id"]:
        if field in payload: setattr(item, field, payload[field])
    if "role" in payload: item.role = Role(payload["role"])
    audit(db, actor.id, "user.updated", "user", item.id, after={"active": item.active, "role": item.role.value}); db.commit(); return {"ok": True}


@router.get("/admin/settings")
def settings_view(user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    return {"settings": {x.key: x.value_json for x in db.query(ApplicationSetting).all()}, "sla_policies": [{c.name: iso(getattr(x,c.name)) for c in x.__table__.columns} for x in db.query(SlaPolicy).all()], "ai_runtime": MODEL_STATUS}


@router.put("/admin/settings/{key}", dependencies=[Depends(verify_csrf)])
def setting_update(key: str, payload: SettingInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    if key not in {"overlap_thresholds", "notification_windows", "demo_banner", "integration_adapters"}: raise HTTPException(422, "Unsupported setting key")
    row = db.get(ApplicationSetting, key) or ApplicationSetting(key=key, value_json={})
    row.value_json, row.updated_by_id = payload.value, user.id; db.add(row); audit(db, user.id, "setting.updated", "setting", key); db.commit(); return {"key": key, "value": row.value_json}


@router.post("/admin/sla", dependencies=[Depends(verify_csrf)])
def upsert_sla(payload: SlaInput, user: User = Depends(require_roles(Role.SYSTEM_ADMIN)), db: Session = Depends(get_db)):
    row = db.query(SlaPolicy).filter_by(category_id=payload.category_id, priority=payload.priority, bureau_id=payload.bureau_id).first() or SlaPolicy(**payload.model_dump())
    row.days = payload.days; db.add(row); audit(db, user.id, "sla.updated", "sla_policy", row.id); db.commit(); return {"id": row.id}


@router.post("/admin/run-sla", dependencies=[Depends(verify_csrf)])
def trigger_sla(user: User = Depends(require_roles(Role.SYSTEM_ADMIN, Role.CENTRAL_ADMIN)), db: Session = Depends(get_db)):
    return run_sla_check(db)

