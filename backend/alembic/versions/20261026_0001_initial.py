"""Initial normalized CaseSync schema and vector extension."""
from alembic import op
from app.core.database import Base
from app.models import *  # noqa: F403

revision = "20261026_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    Base.metadata.create_all(bind)
    if bind.dialect.name == "postgresql":
        op.execute("CREATE INDEX IF NOT EXISTS ix_complaint_embeddings_hnsw ON complaint_embeddings USING hnsw (vector vector_cosine_ops)")


def downgrade():
    bind = op.get_bind()
    Base.metadata.drop_all(bind)


