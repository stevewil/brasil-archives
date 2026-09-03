"""add build_jobs and build_reports (archive-miner work queue)

Revision ID: a1b2c3d4e5f6
Revises: 62af3c38c093
Create Date: 2026-09-03 00:00:00.000000

The archive-miner runs outside this app (dev box / cloud runner); this app
owns the queue + status surface. See app/models/build_job.py and
docs/archive-research-harness.md §4.3.
"""
from alembic import op
import sqlalchemy as sa


revision = 'a1b2c3d4e5f6'
down_revision = '62af3c38c093'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'build_jobs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('kind', sa.String(), nullable=False, server_default='build'),
        sa.Column('construction_mode', sa.String(), nullable=True),
        sa.Column('archive_slug', sa.String(), nullable=True),
        sa.Column('project_slug', sa.String(), nullable=True),
        sa.Column('stage', sa.String(), nullable=False, server_default='triage'),
        sa.Column('status', sa.String(), nullable=False, server_default='queued'),
        sa.Column('checkpoint', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('progress', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('options', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('budget_usd', sa.Numeric(10, 4), nullable=True),
        sa.Column('spent_usd', sa.Numeric(10, 4), nullable=False, server_default='0'),
        sa.Column('build_db_name', sa.String(), nullable=True),
        sa.Column('worker_id', sa.String(), nullable=True),
        sa.Column('heartbeat_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('eta_at', sa.DateTime(), nullable=True),
        sa.Column('operator_note', sa.Text(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.Column('updated_at', sa.DateTime(), nullable=False,
                  server_default=sa.func.current_timestamp()),
    )
    op.create_index('ix_build_jobs_status', 'build_jobs', ['status'])
    op.create_index('ix_build_jobs_archive_slug', 'build_jobs', ['archive_slug'])
    op.create_index('ix_build_jobs_project_slug', 'build_jobs', ['project_slug'])

    op.create_table(
        'build_reports',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('job_id', sa.Integer(),
                  sa.ForeignKey('build_jobs.id', ondelete='CASCADE'),
                  nullable=False),
        sa.Column('at', sa.DateTime(), nullable=False,
                  server_default=sa.func.current_timestamp()),
        sa.Column('stage', sa.String(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False, server_default='{}'),
        sa.Column('summary', sa.Text(), nullable=True),
    )
    op.create_index('ix_build_reports_job_id', 'build_reports', ['job_id'])


def downgrade():
    op.drop_index('ix_build_reports_job_id', 'build_reports')
    op.drop_table('build_reports')
    op.drop_index('ix_build_jobs_project_slug', 'build_jobs')
    op.drop_index('ix_build_jobs_archive_slug', 'build_jobs')
    op.drop_index('ix_build_jobs_status', 'build_jobs')
    op.drop_table('build_jobs')
