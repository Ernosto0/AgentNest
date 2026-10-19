"""Inbox jobs (background-jobs.md). Imported by ``app.handlers.load_handlers``."""

from app.core.config import get_settings
from app.inbox import processing
from app.inbox.models import InboundEvent
from app.inbox.payloads import ProcessInboundEventPayload
from app.jobs.registry import JobContext, job_handler


def _on_dead(job: JobContext, error_code: str) -> None:
    payload = job.payload
    if not isinstance(payload, ProcessInboundEventPayload):
        return
    with job.session_factory() as session:
        event = session.get(InboundEvent, payload.event_id)
        if event is not None and event.status == "received":
            event.status, event.error_code = "failed", error_code
            event.processed_at = job.clock.now()
            session.commit()


@job_handler("process_inbound_event", ProcessInboundEventPayload, max_attempts=3, on_dead=_on_dead)
def process_inbound_event(job: JobContext) -> None:
    payload = job.payload
    if not isinstance(payload, ProcessInboundEventPayload) or job.workspace_id is None:
        return
    with job.session_factory() as session:
        processing.process_inbound_event(
            session,
            job.clock,
            job.workspace_id,
            payload.event_id,
            debounce_seconds=get_settings().reply_debounce_seconds,
        )
