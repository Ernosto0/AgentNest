"""AI evaluation harness (testing-strategy.md §6, ADR-018).

``uv run python -m evals run --all --provider fake`` runs in CI; ``--provider openai`` is run by
hand before changing prompts or models. Datasets are YAML under ``evals/<task>/``.
"""
