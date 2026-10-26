"""Add demo sessions and explicit coordination links.

Revision ID: 20261026_0002
Revises: 20261026_0001
"""

import sqlalchemy as sa

from alembic import op

revision = "20261026_0002"
down_revision = "20261026_0001"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("coordination_records") as batch:
        batch.add_column(sa.Column("source_finding_id", sa.String(length=36), nullable=True))
        batch.add_column(sa.Column("request_key", sa.String(length=120), nullable=True))
        batch.create_foreign_key("fk_coordination_source_finding", "overlap_findings", ["source_finding_id"], ["id"])
        batch.create_index("ix_coordination_records_source_finding_id", ["source_finding_id"])
        batch.create_index("ux_coordination_records_request_key", ["request_key"], unique=True)

    op.create_table(
        "coordination_complaints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("coordination_id", sa.String(length=36), nullable=False),
        sa.Column("complaint_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["coordination_id"], ["coordination_records.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["complaint_id"], ["complaints.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("coordination_id", "complaint_id"),
    )
    op.create_index("ix_coordination_complaints_coordination_id", "coordination_complaints", ["coordination_id"])
    op.create_index("ix_coordination_complaints_complaint_id", "coordination_complaints", ["complaint_id"])

    op.create_table(
        "demo_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("scenario", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="active"),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_by_id", sa.String(length=36), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("complaint_ids", sa.JSON(), nullable=False),
        sa.Column("finding_id", sa.String(length=36), nullable=True),
        sa.Column("coordination_id", sa.String(length=36), nullable=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["institution_id"], ["institutions.id"]),
        sa.ForeignKeyConstraint(["finding_id"], ["overlap_findings.id"]),
        sa.ForeignKeyConstraint(["coordination_id"], ["coordination_records.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demo_sessions_scenario", "demo_sessions", ["scenario"])
    op.create_index("ix_demo_sessions_status", "demo_sessions", ["status"])
    op.create_index("ix_demo_sessions_created_by_id", "demo_sessions", ["created_by_id"])


def downgrade():
    op.drop_index("ix_demo_sessions_created_by_id", table_name="demo_sessions")
    op.drop_index("ix_demo_sessions_status", table_name="demo_sessions")
    op.drop_index("ix_demo_sessions_scenario", table_name="demo_sessions")
    op.drop_table("demo_sessions")
    op.drop_index("ix_coordination_complaints_complaint_id", table_name="coordination_complaints")
    op.drop_index("ix_coordination_complaints_coordination_id", table_name="coordination_complaints")
    op.drop_table("coordination_complaints")
    with op.batch_alter_table("coordination_records") as batch:
        batch.drop_index("ux_coordination_records_request_key")
        batch.drop_index("ix_coordination_records_source_finding_id")
        batch.drop_constraint("fk_coordination_source_finding", type_="foreignkey")
        batch.drop_column("request_key")
        batch.drop_column("source_finding_id")
