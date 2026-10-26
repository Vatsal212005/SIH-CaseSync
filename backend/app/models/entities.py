import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from app.core.database import Base


def now() -> datetime:
    return datetime.now(timezone.utc)


def uid() -> str:
    return str(uuid.uuid4())


class VectorType(TypeDecorator):
    """pgvector in PostgreSQL, JSON in lightweight SQLite tests."""
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector
            return dialect.type_descriptor(Vector(384))
        return dialect.type_descriptor(JSON())


class Role(str, enum.Enum):
    SYSTEM_ADMIN = "system_admin"
    CENTRAL_ADMIN = "central_admin"
    BUREAU_HEAD = "bureau_head"
    CASE_OFFICER = "case_officer"
    AUDITOR = "auditor"


class CaseStatus(str, enum.Enum):
    PENDING = "pending"
    UNDER_PROCESS = "under_process"
    TRANSFERRED = "transferred"
    ESCALATED = "escalated"
    DISPOSED = "disposed"
    REOPENED = "reopened"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReviewState(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"
    UNRELATED = "unrelated"
    RESOLVED = "resolved"


class Bureau(Base):
    __tablename__ = "bureaus"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[Role] = mapped_column(Enum(Role), index=True)
    bureau_id: Mapped[str | None] = mapped_column(ForeignKey("bureaus.id"), nullable=True, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    bureau: Mapped[Bureau | None] = relationship()


class Institution(Base):
    __tablename__ = "institutions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    permanent_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255), index=True)
    normalized_name: Mapped[str] = mapped_column(String(255), index=True)
    address: Mapped[str] = mapped_column(String(500))
    city: Mapped[str] = mapped_column(String(100), index=True)
    state: Mapped[str] = mapped_column(String(100), index=True)
    region: Mapped[str] = mapped_column(String(80), index=True)
    postal_code: Mapped[str] = mapped_column(String(10))
    institution_type: Mapped[str] = mapped_column(String(80), index=True)
    approval_status: Mapped[str] = mapped_column(String(40), index=True)
    contact_email: Mapped[str | None] = mapped_column(String(255))
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    aliases: Mapped[list["InstitutionAlias"]] = relationship(back_populates="institution", cascade="all, delete-orphan")


class InstitutionAlias(Base):
    __tablename__ = "institution_aliases"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(255), index=True)
    normalized_alias: Mapped[str] = mapped_column(String(255), index=True)
    institution: Mapped[Institution] = relationship(back_populates="aliases")
    __table_args__ = (UniqueConstraint("institution_id", "normalized_alias"),)


class ComplaintCategory(Base):
    __tablename__ = "complaint_categories"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Complaint(Base):
    __tablename__ = "complaints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    complaint_no: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    title: Mapped[str] = mapped_column(String(300), index=True)
    description: Mapped[str] = mapped_column(Text)
    category_id: Mapped[str] = mapped_column(ForeignKey("complaint_categories.id"), index=True)
    priority: Mapped[Priority] = mapped_column(Enum(Priority), index=True)
    source: Mapped[str] = mapped_column(String(80))
    stakeholder_type: Mapped[str] = mapped_column(String(80))
    date_received: Mapped[date] = mapped_column(Date, index=True)
    originating_bureau_id: Mapped[str] = mapped_column(ForeignKey("bureaus.id"), index=True)
    assigned_bureau_id: Mapped[str] = mapped_column(ForeignKey("bureaus.id"), index=True)
    assigned_officer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[CaseStatus] = mapped_column(Enum(CaseStatus), index=True)
    latest_action: Mapped[str | None] = mapped_column(String(300))
    next_action: Mapped[str | None] = mapped_column(String(300))
    last_action_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_disposal_date: Mapped[date | None] = mapped_column(Date)
    sla_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    disposal_date: Mapped[date | None] = mapped_column(Date)
    disposal_remarks: Mapped[str | None] = mapped_column(Text)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    institution: Mapped[Institution] = relationship()
    category: Mapped[ComplaintCategory] = relationship()
    originating_bureau: Mapped[Bureau] = relationship(foreign_keys=[originating_bureau_id])
    assigned_bureau: Mapped[Bureau] = relationship(foreign_keys=[assigned_bureau_id])
    assigned_officer: Mapped[User | None] = relationship(foreign_keys=[assigned_officer_id])
    actions: Mapped[list["ComplaintAction"]] = relationship(back_populates="complaint", cascade="all, delete-orphan")
    __table_args__ = (Index("ix_complaint_scope", "assigned_bureau_id", "status", "sla_deadline"),)


class ComplaintAction(Base):
    __tablename__ = "complaint_actions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    action_type: Mapped[str] = mapped_column(String(60), index=True)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str | None] = mapped_column(String(40))
    from_bureau_id: Mapped[str | None] = mapped_column(ForeignKey("bureaus.id"))
    to_bureau_id: Mapped[str | None] = mapped_column(ForeignKey("bureaus.id"))
    remarks: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    complaint: Mapped[Complaint] = relationship(back_populates="actions")
    actor: Mapped[User] = relationship(foreign_keys=[actor_id])


class ComplaintAttachment(Base):
    __tablename__ = "complaint_attachments"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), index=True)
    original_name: Mapped[str] = mapped_column(String(255))
    stored_name: Mapped[str] = mapped_column(String(255), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ComplaintEmbedding(Base):
    __tablename__ = "complaint_embeddings"
    complaint_id: Mapped[str] = mapped_column(ForeignKey("complaints.id", ondelete="CASCADE"), primary_key=True)
    model_name: Mapped[str] = mapped_column(String(160))
    vector: Mapped[list] = mapped_column(VectorType())
    text_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class OverlapFinding(Base):
    __tablename__ = "overlap_findings"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    complaint_a_id: Mapped[str] = mapped_column(ForeignKey("complaints.id"), index=True)
    complaint_b_id: Mapped[str] = mapped_column(ForeignKey("complaints.id"), index=True)
    finding_type: Mapped[str] = mapped_column(String(60), index=True)
    similarity_score: Mapped[float] = mapped_column(Float)
    hybrid_score: Mapped[float] = mapped_column(Float, index=True)
    severity: Mapped[str] = mapped_column(String(30), index=True)
    reasons: Mapped[list] = mapped_column(JSON)
    recommendation: Mapped[str] = mapped_column(Text)
    review_state: Mapped[ReviewState] = mapped_column(Enum(ReviewState), default=ReviewState.PENDING, index=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64), unique=True)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    complaint_a: Mapped[Complaint] = relationship(foreign_keys=[complaint_a_id])
    complaint_b: Mapped[Complaint] = relationship(foreign_keys=[complaint_b_id])


class OverlapReview(Base):
    __tablename__ = "overlap_reviews"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    finding_id: Mapped[str] = mapped_column(ForeignKey("overlap_findings.id", ondelete="CASCADE"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(40))
    notes: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class RelatedCaseLink(Base):
    __tablename__ = "related_case_links"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    complaint_a_id: Mapped[str] = mapped_column(ForeignKey("complaints.id"), index=True)
    complaint_b_id: Mapped[str] = mapped_column(ForeignKey("complaints.id"), index=True)
    relation_type: Mapped[str] = mapped_column(String(40))
    created_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint("complaint_a_id", "complaint_b_id"),)


class CoordinationRecord(Base):
    __tablename__ = "coordination_records"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(255))
    institution_id: Mapped[str] = mapped_column(ForeignKey("institutions.id"), index=True)
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    summary: Mapped[str] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class CoordinationParticipant(Base):
    __tablename__ = "coordination_participants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    coordination_id: Mapped[str] = mapped_column(ForeignKey("coordination_records.id", ondelete="CASCADE"), index=True)
    bureau_id: Mapped[str] = mapped_column(ForeignKey("bureaus.id"))
    user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    __table_args__ = (UniqueConstraint("coordination_id", "bureau_id"),)


class CoordinationActionItem(Base):
    __tablename__ = "coordination_action_items"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    coordination_id: Mapped[str] = mapped_column(ForeignKey("coordination_records.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(255))
    assignee_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    due_date: Mapped[date | None] = mapped_column(Date)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class SlaPolicy(Base):
    __tablename__ = "sla_policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    category_id: Mapped[str | None] = mapped_column(ForeignKey("complaint_categories.id"))
    priority: Mapped[Priority] = mapped_column(Enum(Priority))
    bureau_id: Mapped[str | None] = mapped_column(ForeignKey("bureaus.id"))
    days: Mapped[int] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    __table_args__ = (UniqueConstraint("category_id", "priority", "bureau_id"),)


class Notification(Base):
    __tablename__ = "notifications"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    related_type: Mapped[str | None] = mapped_column(String(40))
    related_id: Mapped[str | None] = mapped_column(String(36), index=True)
    destination: Mapped[str | None] = mapped_column(String(255))
    dedupe_key: Mapped[str | None] = mapped_column(String(255), unique=True)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(36), index=True)
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    request_id: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, index=True)


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON)
    updated_by_id: Mapped[str | None] = mapped_column(ForeignKey("users.id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    kind: Mapped[str] = mapped_column(String(40))
    filename: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40))
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    uploaded_by_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

