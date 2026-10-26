from sqlalchemy.orm import Session

from app.models import AuditEvent, Notification


def audit(db: Session, actor_id: str | None, action: str, entity_type: str, entity_id: str | None, before=None, after=None, request_id=None, ip=None):
    db.add(AuditEvent(actor_id=actor_id, action=action, entity_type=entity_type, entity_id=entity_id, before_json=before, after_json=after, request_id=request_id, ip_address=ip))


def notify(db: Session, recipient_id: str, type_: str, title: str, message: str, related_type=None, related_id=None, destination=None, dedupe_key=None):
    if dedupe_key and db.query(Notification).filter(Notification.dedupe_key == dedupe_key).first():
        return None
    item = Notification(recipient_id=recipient_id, type=type_, title=title, message=message, related_type=related_type, related_id=related_id, destination=destination, dedupe_key=dedupe_key)
    db.add(item)
    return item


