"""Import every module that registers job handlers or approval subjects.

The API enqueues jobs (and ``enqueue`` refuses unknown job types) and the worker runs them, so
both processes call ``load_handlers()`` at startup. Later phases add their modules here.
"""


def load_handlers() -> None:
    import app.ai.jobs  # noqa: F401
    import app.approvals.jobs  # noqa: F401
    import app.commands.jobs  # noqa: F401
    import app.commands.subject  # noqa: F401
    import app.inbox.jobs  # noqa: F401
    import app.inbox.subject  # noqa: F401
    import app.knowledge.extraction  # noqa: F401
