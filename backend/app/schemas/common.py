from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models import Priority, ReviewState, Role


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class LoginInput(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class UserOut(ORMModel):
    id: str
    email: str
    full_name: str
    role: Role
    bureau_id: str | None
    active: bool


class InstitutionInput(BaseModel):
    permanent_id: str = Field(min_length=3, max_length=40)
    name: str = Field(min_length=3, max_length=255)
    aliases: list[str] = []
    address: str = Field(min_length=3, max_length=500)
    city: str
    state: str
    region: str
    postal_code: str = Field(pattern=r"^[0-9]{6}$")
    institution_type: str
    approval_status: str
    contact_email: EmailStr | None = None
    is_synthetic: bool = False


class ComplaintInput(BaseModel):
    institution_id: str
    title: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=20, max_length=15000)
    category_id: str
    priority: Priority
    source: str = Field(min_length=2, max_length=80)
    stakeholder_type: str = Field(min_length=2, max_length=80)
    date_received: date
    assigned_bureau_id: str
    assigned_officer_id: str | None = None


class ComplaintEditInput(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    description: str = Field(min_length=20, max_length=15000)
    category_id: str
    priority: Priority
    next_action: str | None = Field(default=None, max_length=300)


class LinkInput(BaseModel):
    other_complaint_id: str
    relation_type: Literal["related", "duplicate", "shared_institution", "conflicting_action"]
    justification: str = Field(min_length=3, max_length=5000)


class ActionInput(BaseModel):
    action: Literal["start", "remark", "transfer", "accept_transfer", "escalate", "dispose", "reopen", "assign"]
    remarks: str = Field(min_length=3, max_length=5000)
    destination_bureau_id: str | None = None
    officer_id: str | None = None


class ReviewInput(BaseModel):
    decision: ReviewState
    notes: str = Field(min_length=3, max_length=5000)
    create_coordination: bool = True


class CoordinationInput(BaseModel):
    title: str = Field(min_length=5, max_length=255)
    institution_id: str
    summary: str = Field(min_length=5, max_length=5000)
    owner_id: str
    bureau_ids: list[str] = Field(min_length=2)
    complaint_ids: list[str] = Field(min_length=2)
    target_date: date | None = None


class ActionItemInput(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    assignee_id: str
    due_date: date | None = None


class AdminUserInput(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=3, max_length=160)
    password: str = Field(min_length=10, max_length=128)
    role: Role
    bureau_id: str | None = None


class SlaInput(BaseModel):
    category_id: str | None = None
    priority: Priority
    bureau_id: str | None = None
    days: int = Field(ge=1, le=365)


class SettingInput(BaseModel):
    value: dict[str, Any]


class BureauInput(BaseModel):
    code: str = Field(min_length=2, max_length=20, pattern=r"^[A-Z0-9-]+$")
    name: str = Field(min_length=3, max_length=160)
    active: bool = True


class CategoryInput(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    active: bool = True

