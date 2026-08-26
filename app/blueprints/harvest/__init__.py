"""Harvest blueprint — read-only views over aggregated_records + harvest_runs.

Purpose: quick UI to browse what the OAI-PMH harvester has pulled in from
each registered upgrade project. No editing, no re-scoring — this is a
sanity-check surface for archivists and developers.

See ``docs/harvest-design.md`` for the pipeline that populates the store.
"""
from .routes import bp

__all__ = ["bp"]
