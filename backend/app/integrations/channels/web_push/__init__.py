"""Web Push owner channel (ADR-012, F-01 part 2).

Only ``app.integrations.channels.registry`` imports this package (import-linter), and only
``sender`` imports ``pywebpush``. ``payloads`` builds the push body from a fixed template per
notification type and never reads customer text.
"""
