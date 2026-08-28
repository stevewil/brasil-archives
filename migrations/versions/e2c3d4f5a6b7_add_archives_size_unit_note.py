"""add archives.size_unit_note

Revision ID: e2c3d4f5a6b7
Revises: d7f1a2b3c4d5
Create Date: 2026-08-27 00:00:00.000000

Free-text audit trail for the Scale dimension (docs/algorithm-v1.md
§Dimension 7): what unit an archive counts in (processos vs. images vs.
page-equivalents vs. items). Previously carried in the calibration YAML
only and dropped by scripts/load_calibration.py with a warning; now a
first-class Archive column alongside curatorial_rarity_notes and
prior_use_note. Backfilled from configs/calibration/pass2.yaml on the
next `python -m scripts.load_calibration` run.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2c3d4f5a6b7'
down_revision = 'd7f1a2b3c4d5'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('archives', schema=None) as batch_op:
        batch_op.add_column(sa.Column('size_unit_note', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('archives', schema=None) as batch_op:
        batch_op.drop_column('size_unit_note')
