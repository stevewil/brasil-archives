"""add archives.last_probed_at (quarterly health probe)

Revision ID: d7f1a2b3c4d5
Revises: ca94209a1f1b
Create Date: 2026-08-27 00:00:00.000000

The four probe-fed facets (web ops health, external preservation, growth
signal, prior-use signal) are written to ``facet_values`` by
``app/services/probe.py``. This column records when the archive was last
probed so the UI can show a freshness stamp per algorithm-v1.md
§"Ongoing infrastructure" ("log a last_probed timestamp per archive").
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd7f1a2b3c4d5'
down_revision = 'ca94209a1f1b'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('archives', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_probed_at', sa.DateTime(), nullable=True))


def downgrade():
    with op.batch_alter_table('archives', schema=None) as batch_op:
        batch_op.drop_column('last_probed_at')
