"""Reporting (Phase 6): the deterministic daily report.

Every number is a SQL aggregation over persisted records (INV-08); the language model is never
involved. Reads other modules' models only: it must not import operations services, commands or
the API layer, and only command executors, the API router and ``app.demo`` import it.
"""
