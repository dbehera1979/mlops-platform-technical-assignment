from alembic import op
import sqlalchemy as sa


revision = '81f5c4cf3bce'
down_revision = '0a1dea05ee52'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'deployment_events',
        sa.Column('reconciled', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    with op.batch_alter_table('deployment_events') as batch_op:
        batch_op.alter_column('reconciled', server_default=None)


def downgrade() -> None:
    op.drop_column('deployment_events', 'reconciled')