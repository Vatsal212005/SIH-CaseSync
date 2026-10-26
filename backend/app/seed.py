"""Deterministic synthetic dataset for demonstrations. No official AICTE data is used."""
import random
from datetime import date, datetime, timedelta, timezone

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import hash_password
from app.models import *
from app.services.overlap import detect_overlaps

SEED_VERSION = "2026.10.1"
STATES = [
    ("Maharashtra", "Western", "Pune"), ("Gujarat", "Western", "Ahmedabad"),
    ("Karnataka", "South-West", "Bengaluru"), ("Tamil Nadu", "Southern", "Chennai"),
    ("Telangana", "South-Central", "Hyderabad"), ("Delhi", "Northern", "New Delhi"),
    ("Uttar Pradesh", "Northern", "Lucknow"), ("West Bengal", "Eastern", "Kolkata"),
    ("Odisha", "Eastern", "Bhubaneswar"), ("Rajasthan", "North-West", "Jaipur"),
]
CATEGORIES = ["Unauthorized fee collection", "Faculty grievances", "Infrastructure deficiencies", "Approval/regulatory violations", "Admission irregularities", "Examination-related grievances", "Student welfare", "Institutional compliance", "Other"]
ISSUES = {
    "Unauthorized fee collection": ["students were asked to pay an additional laboratory development charge not listed in the approved fee schedule", "the institution collected an unapproved mandatory development fee from the current student cohort"],
    "Faculty grievances": ["faculty members report delayed salary payments and missing employment records", "teaching staff allege salary arrears and irregular service documentation"],
    "Infrastructure deficiencies": ["laboratory equipment and fire safety facilities are below the declared capacity", "inspection reports indicate insufficient laboratories and incomplete safety arrangements"],
    "Approval/regulatory violations": ["a programme appears to operate beyond the approved intake and declared campus", "the institution may be admitting students beyond its sanctioned programme capacity"],
    "Admission irregularities": ["admission records show possible deviations from the published counselling procedure", "students report admissions outside the declared eligibility and counselling rules"],
    "Examination-related grievances": ["semester results were withheld without a documented academic reason", "students report unexplained delays and withholding of examination results"],
    "Student welfare": ["students report inadequate grievance support and unsafe hostel conditions", "hostel residents describe safety concerns and an unavailable grievance channel"],
    "Institutional compliance": ["mandatory disclosure and faculty records were not updated for the current session", "the public disclosure page omits current compliance and faculty information"],
    "Other": ["a stakeholder requested administrative review of institution operations", "a general institution governance concern requires preliminary verification"],
}


def seed():
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        existing = db.get(ApplicationSetting, "seed_version")
        if existing and existing.value_json.get("version") == SEED_VERSION:
            print(f"Synthetic dataset {SEED_VERSION} already present; no changes made.")
            return
        if not settings.demo_mode:
            print("DEMO_MODE is disabled; seed command intentionally did not create demo identities or records.")
            return
        rng = random.Random(26264)
        bureau_specs = [("RB", "Regulation Bureau"), ("PGRC", "Public Grievance Redressal Cell"), ("AB", "Approval Bureau"), ("SWC", "Student Welfare Cell")]
        bureaus = []
        for code, name in bureau_specs:
            row = db.query(Bureau).filter_by(code=code).first() or Bureau(code=code, name=name)
            db.add(row); bureaus.append(row)
        db.flush()
        users = []
        user_specs = [
            ("admin@casesync.demo", "Demo System Administrator", Role.SYSTEM_ADMIN, None),
            ("central@casesync.demo", "Demo Central Administrator", Role.CENTRAL_ADMIN, None),
            ("auditor@casesync.demo", "Demo Read-Only Auditor", Role.AUDITOR, None),
        ]
        for bureau in bureaus:
            user_specs.append((f"head.{bureau.code.lower()}@casesync.demo", f"Demo {bureau.code} Bureau Head", Role.BUREAU_HEAD, bureau.id))
            for n in range(1, 4): user_specs.append((f"officer{n}.{bureau.code.lower()}@casesync.demo", f"Demo {bureau.code} Officer {n}", Role.CASE_OFFICER, bureau.id))
        password_hash = hash_password(settings.demo_password)
        for email, name, role, bureau_id in user_specs:
            row = db.query(User).filter_by(email=email).first() or User(email=email, full_name=name, role=role, bureau_id=bureau_id, password_hash=password_hash)
            db.add(row); users.append(row)
        categories = []
        for name in CATEGORIES:
            row = db.query(ComplaintCategory).filter_by(name=name).first() or ComplaintCategory(name=name)
            db.add(row); categories.append(row)
        db.flush()
        officers = [u for u in users if u.role == Role.CASE_OFFICER]
        institutions = []
        prefixes = ["Aarohan", "Blue River", "Civic Horizon", "Dawn Valley", "Evergreen", "Frontier", "Greenfield", "Harmony", "Insight", "Jagruti"]
        kinds = ["Institute of Technology", "College of Engineering", "School of Management", "Polytechnic", "Technical Education Centre"]
        for i in range(100):
            permanent_id = f"DEMO-AICTE-{i+1:05d}"
            row = db.query(Institution).filter_by(permanent_id=permanent_id).first()
            if not row:
                state, region, city = STATES[i % len(STATES)]
                name = f"DEMO {prefixes[i % len(prefixes)]} {kinds[(i // 10) % len(kinds)]} {i+1:03d}"
                row = Institution(permanent_id=permanent_id, name=name, normalized_name=name.lower(), address=f"Synthetic Campus Road {i+1}, Demonstration District", city=city, state=state, region=region, postal_code=f"{100000+i:06d}", institution_type=kinds[(i // 10) % len(kinds)], approval_status=["Approved", "Under Review", "Conditional"][i % 3], contact_email=None, is_synthetic=True)
                db.add(row); db.flush()
                db.add(InstitutionAlias(institution_id=row.id, alias=f"DEMO {prefixes[i % 10]} Tech {i+1}", normalized_alias=f"demo {prefixes[i % 10].lower()} tech {i+1}"))
            institutions.append(row)
        db.flush()
        for priority in Priority:
            days = {Priority.LOW: 45, Priority.MEDIUM: 30, Priority.HIGH: 15, Priority.CRITICAL: 7}[priority]
            if not db.query(SlaPolicy).filter_by(category_id=None, priority=priority, bureau_id=None).first(): db.add(SlaPolicy(priority=priority, days=days))
        db.flush()
        if db.query(Complaint).filter(Complaint.is_synthetic.is_(True)).count() < 1000:
            statuses = [CaseStatus.PENDING]*24 + [CaseStatus.UNDER_PROCESS]*35 + [CaseStatus.TRANSFERRED]*8 + [CaseStatus.ESCALATED]*8 + [CaseStatus.DISPOSED]*22 + [CaseStatus.REOPENED]*3
            base_date = date(2026, 1, 1)
            complaints = []
            for i in range(1000):
                inst = institutions[(i * 37 + i // 11) % 100]
                category = categories[(i * 5 + i // 17) % len(categories)]
                bureau = bureaus[(i + i // 7) % len(bureaus)]
                officer_pool = [u for u in officers if u.bureau_id == bureau.id]
                received = base_date + timedelta(days=(i * 13) % 285)
                status = statuses[(i * 17) % len(statuses)]
                variant = ISSUES[category.name][i % 2]
                # Intentional, computed cross-bureau paraphrase pairs share institution/category every 50 records.
                if i % 50 == 1:
                    prev = complaints[-1]; inst = prev.institution; category = prev.category; bureau = bureaus[(bureaus.index(prev.assigned_bureau)+1) % len(bureaus)]; officer_pool = [u for u in officers if u.bureau_id == bureau.id]; variant = ISSUES[category.name][1]
                priority = [Priority.LOW, Priority.MEDIUM, Priority.HIGH, Priority.CRITICAL][(i * 3) % 4]
                deadline = datetime.combine(received, datetime.min.time(), timezone.utc) + timedelta(days={Priority.LOW:45, Priority.MEDIUM:30, Priority.HIGH:15, Priority.CRITICAL:7}[priority])
                title = f"{category.name} review — synthetic case {i+1:04d}"
                item = Complaint(complaint_no=f"CMP-2026-{i+1:06d}", institution=inst, title=title, description=f"Synthetic demonstration complaint: {variant}. Record {i+1} contains no real complainant or institution information.", category=category, priority=priority, source=["CPGRAMS adapter", "Email intake", "Portal", "Bureau referral"][i%4], stakeholder_type=["Student", "Faculty", "Parent", "Public official"][i%4], date_received=received, originating_bureau_id=bureau.id, assigned_bureau=bureau, assigned_officer=rng.choice(officer_pool), status=status, latest_action="Synthetic workflow activity recorded", next_action="Review evidence and record official action", last_action_at=datetime.combine(received, datetime.min.time(), timezone.utc)+timedelta(days=2), expected_disposal_date=deadline.date(), sla_deadline=deadline, disposal_date=(received+timedelta(days=10) if status == CaseStatus.DISPOSED else None), disposal_remarks=("Closed after synthetic document review" if status == CaseStatus.DISPOSED else None), is_synthetic=True, created_by_id=users[1].id, created_at=datetime.combine(received, datetime.min.time(), timezone.utc))
                db.add(item); complaints.append(item)
                if (i+1) % 100 == 0: db.flush()
            db.flush()
            for i, item in enumerate(complaints):
                db.add(ComplaintAction(complaint_id=item.id, actor_id=item.assigned_officer_id, action_type="registered", to_status=CaseStatus.PENDING.value, to_bureau_id=item.originating_bureau_id, remarks="Synthetic complaint registered", created_at=item.created_at))
                if item.status != CaseStatus.PENDING: db.add(ComplaintAction(complaint_id=item.id, actor_id=item.assigned_officer_id, action_type="workflow_update", from_status=CaseStatus.PENDING.value, to_status=item.status.value, from_bureau_id=item.originating_bureau_id, to_bureau_id=item.assigned_bureau_id, remarks="Deterministic synthetic lifecycle transition", created_at=item.last_action_at))
            db.commit()
            # Real rules and similarity scoring calculate findings; outcomes are not seeded.
            for item in complaints:
                if item.complaint_no.endswith("001") or int(item.complaint_no[-6:]) % 50 == 2:
                    detect_overlaps(db, item)
            db.commit()
        central = db.query(User).filter_by(email="central@casesync.demo").one()
        sample_inst = institutions[0]
        if not db.query(CoordinationRecord).first():
            coord = CoordinationRecord(title="DEMO multi-bureau fee review", institution_id=sample_inst.id, owner_id=central.id, status="open", summary="Synthetic coordination record demonstrating shared investigation ownership.", target_date=date.today()+timedelta(days=14)); db.add(coord); db.flush()
            for bureau in bureaus[:2]: db.add(CoordinationParticipant(coordination_id=coord.id, bureau_id=bureau.id))
            db.add(CoordinationActionItem(coordination_id=coord.id, title="Compare synthetic notices issued by participating bureaus", assignee_id=officers[0].id, due_date=date.today()+timedelta(days=7)))
        for idx, user in enumerate(users[:7]):
            key = f"seed-welcome:{user.id}"
            if not db.query(Notification).filter_by(dedupe_key=key).first(): db.add(Notification(recipient_id=user.id, type="system", title="Synthetic demonstration workspace", message="All demo institutions, complaints and identities are fictional. No official AICTE dataset is connected.", destination="/overview", dedupe_key=key))
        defaults = {
            "seed_version": {"version": SEED_VERSION, "synthetic": True},
            "overlap_thresholds": {"shared_activity": 0.42, "related": 0.55, "likely_duplicate": 0.82},
            "integration_adapters": {"csv": {"enabled": True}, "official_api": {"enabled": False, "status": "awaiting_authorized_credentials"}},
            "demo_banner": {"enabled": True, "text": "Synthetic demonstration data — not an official AICTE deployment"},
        }
        for key, value in defaults.items():
            row = db.get(ApplicationSetting, key) or ApplicationSetting(key=key, value_json=value)
            row.value_json = value; db.add(row)
        db.commit()
        print(f"Seeded deterministic synthetic dataset {SEED_VERSION}: {db.query(Institution).count()} institutions, {db.query(Complaint).count()} complaints, {db.query(OverlapFinding).count()} computed overlap findings.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()

