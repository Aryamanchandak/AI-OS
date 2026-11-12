"""Initial durable run schema."""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None

def upgrade():
    op.create_table("runs", sa.Column("id", sa.String(36), primary_key=True), sa.Column("status", sa.String(40), nullable=False), sa.Column("batch_json", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("error", sa.Text), sa.Column("warning_count", sa.Integer, nullable=False, server_default="0"))
    op.create_index("ix_runs_status", "runs", ["status"])
    op.create_table("events", sa.Column("id", sa.Integer, primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False), sa.Column("sequence", sa.Integer, nullable=False), sa.Column("stage", sa.String(60), nullable=False), sa.Column("message", sa.Text, nullable=False), sa.Column("kind", sa.String(20), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("run_id", "sequence"))
    op.create_index("ix_events_run_id", "events", ["run_id"])
    op.create_table("artifacts", sa.Column("id", sa.Integer, primary_key=True), sa.Column("run_id", sa.String(36), sa.ForeignKey("runs.id"), nullable=False), sa.Column("kind", sa.String(60), nullable=False), sa.Column("artifact_key", sa.String(120), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("payload_json", sa.Text, nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("run_id", "kind", "artifact_key", "version"))
    op.create_index("ix_artifacts_run_id", "artifacts", ["run_id"])
    op.create_index("ix_artifacts_kind", "artifacts", ["kind"])

def downgrade():
    op.drop_table("artifacts"); op.drop_table("events"); op.drop_table("runs")
