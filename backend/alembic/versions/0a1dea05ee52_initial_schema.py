from alembic import op
import sqlalchemy as sa


revision = '0a1dea05ee52'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('models',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('name', sa.String(length=200), nullable=False),
    sa.Column('description', sa.String(length=1000), nullable=True),
    sa.Column('owner_team', sa.String(length=200), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_models_name'), 'models', ['name'], unique=True)
    op.create_table('model_versions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('model_id', sa.String(length=36), nullable=False),
    sa.Column('version_label', sa.String(length=50), nullable=False),
    sa.Column('framework', sa.String(length=100), nullable=False),
    sa.Column('algorithm', sa.String(length=100), nullable=False),
    sa.Column('artifact_uri', sa.String(length=500), nullable=False),
    sa.Column('training_data_ref', sa.String(length=500), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=False),
    sa.Column('lifecycle_stage', sa.Enum('DRAFT', 'VALIDATED', 'APPROVED', 'STAGING', 'PRODUCTION', 'ARCHIVED', name='lifecyclestage'), nullable=False),
    sa.Column('created_by', sa.String(length=200), nullable=True),
    sa.Column('row_version', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['model_id'], ['models.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('model_id', 'version_label', name='uq_model_version_label')
    )
    op.create_index(op.f('ix_model_versions_lifecycle_stage'), 'model_versions', ['lifecycle_stage'], unique=False)
    op.create_index(op.f('ix_model_versions_model_id'), 'model_versions', ['model_id'], unique=False)
    op.create_table('approval_records',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('model_version_id', sa.String(length=36), nullable=False),
    sa.Column('from_stage', sa.Enum('DRAFT', 'VALIDATED', 'APPROVED', 'STAGING', 'PRODUCTION', 'ARCHIVED', name='lifecyclestage'), nullable=False),
    sa.Column('to_stage', sa.Enum('DRAFT', 'VALIDATED', 'APPROVED', 'STAGING', 'PRODUCTION', 'ARCHIVED', name='lifecyclestage'), nullable=False),
    sa.Column('approved_by', sa.String(length=200), nullable=False),
    sa.Column('decision', sa.Enum('APPROVED', 'REJECTED', name='approvaldecision'), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_approval_records_model_version_id'), 'approval_records', ['model_version_id'], unique=False)
    op.create_table('deployments',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('model_version_id', sa.String(length=36), nullable=False),
    sa.Column('environment', sa.String(length=50), nullable=False),
    sa.Column('status', sa.Enum('REQUESTED', 'VALIDATING', 'DEPLOYING', 'SUCCEEDED', 'FAILED', 'ROLLED_BACK', name='deploymentstatus'), nullable=False),
    sa.Column('idempotency_key', sa.String(length=200), nullable=False),
    sa.Column('requested_by', sa.String(length=200), nullable=True),
    sa.Column('current_attempt', sa.Integer(), nullable=False),
    sa.Column('previous_deployment_id', sa.String(length=36), nullable=True),
    sa.Column('failure_reason', sa.String(length=1000), nullable=True),
    sa.Column('failure_class', sa.Enum('TRANSIENT', 'TERMINAL', name='failureclass'), nullable=True),
    sa.Column('is_rollback', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ),
    sa.ForeignKeyConstraint(['previous_deployment_id'], ['deployments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deployments_environment'), 'deployments', ['environment'], unique=False)
    op.create_index(op.f('ix_deployments_idempotency_key'), 'deployments', ['idempotency_key'], unique=True)
    op.create_index(op.f('ix_deployments_model_version_id'), 'deployments', ['model_version_id'], unique=False)
    op.create_index(op.f('ix_deployments_status'), 'deployments', ['status'], unique=False)
    op.create_table('metric_snapshots',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('model_version_id', sa.String(length=36), nullable=False),
    sa.Column('environment', sa.String(length=50), nullable=False),
    sa.Column('latency_ms_p50', sa.Float(), nullable=True),
    sa.Column('latency_ms_p99', sa.Float(), nullable=True),
    sa.Column('throughput_rps', sa.Float(), nullable=True),
    sa.Column('error_rate', sa.Float(), nullable=True),
    sa.Column('quality_score', sa.Float(), nullable=True),
    sa.Column('drift_score', sa.Float(), nullable=True),
    sa.Column('availability', sa.Float(), nullable=True),
    sa.Column('last_successful_inference_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('recorded_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['model_version_id'], ['model_versions.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_metric_snapshots_environment'), 'metric_snapshots', ['environment'], unique=False)
    op.create_index(op.f('ix_metric_snapshots_model_version_id'), 'metric_snapshots', ['model_version_id'], unique=False)
    op.create_index(op.f('ix_metric_snapshots_recorded_at'), 'metric_snapshots', ['recorded_at'], unique=False)
    op.create_table('deployment_events',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('deployment_id', sa.String(length=36), nullable=False),
    sa.Column('from_status', sa.String(length=20), nullable=True),
    sa.Column('to_status', sa.String(length=20), nullable=False),
    sa.Column('message', sa.String(length=1000), nullable=True),
    sa.Column('correlation_id', sa.String(length=100), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['deployment_id'], ['deployments.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_deployment_events_created_at'), 'deployment_events', ['created_at'], unique=False)
    op.create_index(op.f('ix_deployment_events_deployment_id'), 'deployment_events', ['deployment_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_deployment_events_deployment_id'), table_name='deployment_events')
    op.drop_index(op.f('ix_deployment_events_created_at'), table_name='deployment_events')
    op.drop_table('deployment_events')
    op.drop_index(op.f('ix_metric_snapshots_recorded_at'), table_name='metric_snapshots')
    op.drop_index(op.f('ix_metric_snapshots_model_version_id'), table_name='metric_snapshots')
    op.drop_index(op.f('ix_metric_snapshots_environment'), table_name='metric_snapshots')
    op.drop_table('metric_snapshots')
    op.drop_index(op.f('ix_deployments_status'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_model_version_id'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_idempotency_key'), table_name='deployments')
    op.drop_index(op.f('ix_deployments_environment'), table_name='deployments')
    op.drop_table('deployments')
    op.drop_index(op.f('ix_approval_records_model_version_id'), table_name='approval_records')
    op.drop_table('approval_records')
    op.drop_index(op.f('ix_model_versions_model_id'), table_name='model_versions')
    op.drop_index(op.f('ix_model_versions_lifecycle_stage'), table_name='model_versions')
    op.drop_table('model_versions')
    op.drop_index(op.f('ix_models_name'), table_name='models')
    op.drop_table('models')