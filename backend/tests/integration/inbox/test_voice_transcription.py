"""F-03 Session 01: a voice note is downloaded (capped, outside any transaction), transcribed and
stored with its metadata; every failure leaves the message on the existing human path with a
reason code. Offline: the mock fetcher and the fake provider, never a key or the network."""

import uuid
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select

from app.audit.models import AuditLog
from app.demo import simulator
from app.inbox.models import InboundEvent, Message, MessageTranscript, ReplyDraft
from app.inbox.payloads import TranscribeVoiceNotePayload
from app.integrations.instagram import webhook_format as wf
from app.integrations.llm import FakeLLMProvider
from app.integrations.transcription import (
    FakeTranscriptionProvider,
    FixtureAudioFetcher,
    override_transcription,
)
from app.integrations.transcription.base import AudioClip, FetchedAudio, TranscriptionResult
from app.integrations.transcription.errors import (
    TranscriptionRejected,
    TranscriptionTransientError,
)
from app.jobs.models import Job
from app.jobs.queue import enqueue
from tests.helpers.publishing import GuardedFactory
from tests.integration.inbox.conftest import InboxEnv


def voice(fixture: str = "price_question_tr") -> list[dict[str, Any]]:
    return [wf.audio_attachment(f"mock-audio://{fixture}")]


def deliver_voice(
    inbox: InboxEnv, fixture: str = "price_question_tr", **kwargs: Any
) -> MessageTranscript | None:
    kwargs.setdefault("mid", f"voice-{uuid.uuid4().hex[:8]}")
    response = inbox.deliver_and_process(None, attachments=voice(fixture), **kwargs)
    assert response.status_code == 200, response.text
    return transcript_of(inbox, kwargs["mid"])


def transcript_of(inbox: InboxEnv, mid: str) -> MessageTranscript | None:
    inbox.session.expire_all()
    return inbox.session.scalars(
        select(MessageTranscript)
        .join(Message, Message.id == MessageTranscript.message_id)
        .where(Message.external_message_id == mid)
    ).one_or_none()


def transcript_jobs(inbox: InboxEnv) -> list[Job]:
    return inbox.jobs("transcribe_voice_note")


@pytest.fixture
def fake() -> Iterator[FakeTranscriptionProvider]:
    provider = FakeTranscriptionProvider()
    with override_transcription(transcriber=provider):
        yield provider


# --- success ------------------------------------------------------------------------------------


def test_a_voice_note_is_transcribed_and_stored_with_its_metadata(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None
    assert (row.status, row.reason_code, row.source) == ("succeeded", None, "transcript")
    assert row.text == "Merhaba, aylık üyelik ücreti ne kadar acaba?"
    assert (row.language, row.provider, row.model) == ("tr", "fake", "fake")
    assert row.duration_seconds == 6.0 and (row.audio_bytes or 0) > 0
    assert row.is_simulated is True and row.completed_at == inbox.clock.now()
    assert row.erased_at is None
    assert fake.models == [inbox.settings.transcription_model]  # the model comes from settings
    (message,) = inbox.messages()
    assert row.message_id == message.id and row.workspace_id == inbox.env.workspace.id
    # The message itself is untouched: still an attachment-only message with no text.
    assert message.text is None and message.attachments[0]["type"] == "audio"


def test_the_transcript_never_becomes_the_message_text(
    inbox: InboxEnv, fake: FakeTranscriptionProvider, provider: FakeLLMProvider
) -> None:
    inbox.seed_facts()
    deliver_voice(inbox, "price_question_tr", mid="v-1")
    inbox.draft_now()
    (message,) = inbox.messages()
    assert message.text is None  # the words live in message_transcripts, labelled as a transcript
    draft = inbox.draft()
    assert draft is not None
    # Session 02: the transcript is drafted from, and the reply always needs a person.
    assert draft.status == "pending_approval"
    assert "TRANSCRIPT_REQUIRES_APPROVAL" in draft.decision_reasons
    assert draft.validation["transcript_message_ids"] == [str(message.id)]


def test_english_and_disfluent_transcripts_get_a_language(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    english = deliver_voice(inbox, "english_question", mid="v-en")
    turkish = deliver_voice(inbox, "disfluent_tr", mid="v-tr", customer="cust-2")
    assert english is not None and english.language == "en"
    assert turkish is not None and turkish.language == "tr"
    assert "ıı" in (turkish.text or "")  # disfluencies are kept as the provider heard them


def test_success_and_failure_are_audited_without_the_transcript_text(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    deliver_voice(inbox, "price_question_tr", mid="v-1")
    deliver_voice(inbox, "expired", mid="v-2", customer="cust-2")
    inbox.session.expire_all()
    ok_entry = inbox.session.scalars(
        select(AuditLog).where(AuditLog.action == "message.transcribed")
    ).one()
    failed = inbox.session.scalars(
        select(AuditLog).where(AuditLog.action == "message.transcription_failed")
    ).one()
    assert ok_entry.metadata_["provider"] == "fake" and ok_entry.is_simulated
    assert failed.metadata_["reason"] == "VOICE_EXPIRED"
    assert "ücret" not in str(ok_entry.metadata_) and "text" not in ok_entry.metadata_
    assert ok_entry.workspace_id == inbox.env.workspace.id


def test_the_job_payload_and_row_hold_ids_only_never_the_url_or_the_audio(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    deliver_voice(inbox, "price_question_tr", mid="v-1")
    (job,) = transcript_jobs(inbox)
    assert set(job.payload) == {"message_id"}
    assert "mock-audio" not in str(job.payload) and job.status == "succeeded"


def test_the_demo_script_delivers_a_voice_note_that_gets_transcribed(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    script = simulator.get_script("voice_note")
    assert script.text is None and script.attachments[0]["type"] == "audio"
    simulator.simulate_customer_message(
        inbox.factory,
        inbox.clock,
        inbox.settings,
        inbox.env.workspace.id,
        customer_alias=script.customer_alias,
        text=script.text,
        attachments=script.attachments,
    )
    inbox.process()
    inbox.session.expire_all()
    (row,) = inbox.session.scalars(select(MessageTranscript)).all()
    assert row.status == "succeeded" and row.text and row.is_simulated


# --- real-shaped payloads over the mock account ------------------------------------------------


def test_a_real_shaped_payload_is_parsed_but_the_mock_account_never_touches_the_network(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    payload = {
        "object": "instagram",
        "entry": [
            {
                "id": inbox.account.external_account_id,
                "time": 1,
                "messaging": [
                    {
                        "sender": {"id": "cust-1"},
                        "recipient": {"id": inbox.account.external_account_id},
                        "timestamp": 1,
                        "message": {
                            "mid": "real-1",
                            "attachments": [
                                {
                                    "type": "audio",
                                    "payload": {"url": "https://scontent.cdninstagram.com/a.mp4"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    inbox._open_simulated_window(payload)
    assert inbox.post(payload).status_code == 200
    inbox.process()
    row = transcript_of(inbox, "real-1")
    assert row is not None and (row.status, row.reason_code) == ("failed", "VOICE_URL_REFUSED")
    assert fake.calls == []


# --- failures stay on the human path --------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "reason", "provider_called"),
    [
        ("expired", "VOICE_EXPIRED", False),
        ("oversize", "VOICE_TOO_LARGE", False),
        ("notaudio", "VOICE_UNSUPPORTED_TYPE", False),
        ("toolong", "VOICE_TOO_LONG", False),
        ("silence", "VOICE_NO_SPEECH", True),
    ],
)
def test_a_failed_voice_note_stays_a_person_handled_attachment_with_a_reason(
    inbox: InboxEnv,
    fake: FakeTranscriptionProvider,
    fixture: str,
    reason: str,
    provider_called: bool,
) -> None:
    inbox.seed_facts()
    row = deliver_voice(inbox, fixture, mid="v-1")
    assert row is not None
    assert (row.status, row.reason_code, row.text) == ("failed", reason, None)
    assert bool(fake.calls) is provider_called
    inbox.draft_now()
    draft = inbox.draft()
    assert draft is not None and (draft.status, draft.decision_reasons) == (
        "needs_human",
        ["ATTACHMENT_ONLY"],
    )
    (job,) = transcript_jobs(inbox)
    assert job.status == "succeeded"  # a permanent failure is recorded, not retried


def test_a_voice_note_without_a_url_fails_at_once_and_queues_no_job(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    inbox.deliver_and_process(None, attachments=[{"type": "audio", "url": ""}], mid="v-1")
    row = transcript_of(inbox, "v-1")
    assert row is not None and (row.status, row.reason_code) == ("failed", "VOICE_URL_MISSING")
    assert transcript_jobs(inbox) == [] and fake.calls == []


def test_a_clip_longer_than_the_limit_is_refused_before_the_provider_call(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    with override_transcription(
        settings=inbox.settings.model_copy(update={"transcription_max_audio_seconds": 5})
    ):
        row = deliver_voice(inbox, "price_question_tr", mid="v-1")  # 6 s
    assert row is not None and row.reason_code == "VOICE_TOO_LONG" and fake.calls == []
    assert row.provider is None  # nothing was sent anywhere


def test_the_size_cap_comes_from_settings(inbox: InboxEnv, fake: FakeTranscriptionProvider) -> None:
    with override_transcription(
        settings=inbox.settings.model_copy(update={"transcription_max_audio_bytes": 10})
    ):
        row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None and row.reason_code == "VOICE_TOO_LARGE" and fake.calls == []


def test_a_provider_that_reports_a_longer_duration_than_the_limit_is_discarded(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    class Opaque:
        """A fetcher whose audio has no readable duration (an unknown container)."""

        def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedAudio:
            return FetchedAudio(b"OggS\x00\x02" + b"\x00" * 64, "audio/ogg")

    fake.queue(TranscriptionResult("uzun", "tr", 999.0, "fake", "fake", True, 1))
    with override_transcription(mock_fetcher=Opaque()):
        row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None and (row.status, row.reason_code) == ("failed", "VOICE_TOO_LONG")
    assert row.text is None and row.provider == "fake"  # the call happened and counts for the quota


def test_a_provider_refusal_is_recorded_not_retried(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    fake.queue(TranscriptionRejected())
    row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None and row.reason_code == "VOICE_TRANSCRIPTION_REJECTED"
    assert len(fake.calls) == 1


def test_a_transient_provider_error_is_retried_and_then_succeeds(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    fake.queue(TranscriptionTransientError("down"))
    fake.queue(TranscriptionTransientError("rate limited", retry_after_seconds=3))
    inbox.deliver(None, attachments=voice(), mid="v-1")
    inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None and row.status == "pending"  # waiting for the retry
    (job,) = transcript_jobs(inbox)
    assert (job.status, job.attempts, job.last_error_code) == (
        "queued",
        1,
        "VOICE_TRANSCRIPTION_UNAVAILABLE",
    )
    inbox.clock.advance(timedelta(seconds=15))  # the first backoff is 10 s, give or take 20 %
    inbox.process()
    inbox.clock.advance(timedelta(seconds=4))  # the provider's Retry-After was 3 s
    inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None and row.status == "succeeded" and len(fake.calls) == 3


def test_when_every_retry_fails_the_row_fails_and_the_job_is_dead_and_visible(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    for _ in range(3):
        fake.queue(TranscriptionTransientError("down"))
    inbox.deliver(None, attachments=voice(), mid="v-1")
    for wait in (0, 15, 80):  # backoff 10 s then 60 s, each with +/- 20 % jitter
        inbox.clock.advance(timedelta(seconds=wait))
        inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None
    assert (row.status, row.reason_code) == ("failed", "VOICE_TRANSCRIPTION_UNAVAILABLE")
    (job,) = transcript_jobs(inbox)
    assert job.status == "dead"  # INV-13: a dead job is visible


def test_a_download_that_keeps_failing_ends_as_a_download_failure(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    inbox.deliver(None, attachments=voice("unreachable"), mid="v-1")
    for wait in (0, 15, 80):  # backoff 10 s then 60 s, each with +/- 20 % jitter
        inbox.clock.advance(timedelta(seconds=wait))
        inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None and row.reason_code == "VOICE_DOWNLOAD_FAILED"
    assert fake.calls == []


def test_an_unexpected_error_leaves_the_message_on_the_human_path(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    fake.queue(RuntimeError("bug"))  # not a typed provider error
    row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None
    assert (row.status, row.reason_code) == ("failed", "VOICE_TRANSCRIPTION_UNAVAILABLE")
    (job,) = transcript_jobs(inbox)
    assert job.status == "dead" and "mock-audio" not in str(job.last_error_detail)


# --- the rules around the call ------------------------------------------------------------------


def test_no_download_or_provider_call_happens_inside_a_transaction(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    guarded = GuardedFactory(inbox.factory)
    open_during: list[tuple[str, int]] = []

    class SpyFetcher(FixtureAudioFetcher):
        def fetch(self, url: str, *, max_bytes: int, timeout_s: float) -> FetchedAudio:
            open_during.append(("fetch", guarded.open_transactions()))
            return super().fetch(url, max_bytes=max_bytes, timeout_s=timeout_s)

    class SpyProvider(FakeTranscriptionProvider):
        def transcribe_audio(
            self, clip: AudioClip, *, model: str, timeout_s: float
        ) -> TranscriptionResult:
            open_during.append(("transcribe", guarded.open_transactions()))
            return super().transcribe_audio(clip, model=model, timeout_s=timeout_s)

    inbox.deliver(None, attachments=voice(), mid="v-1")
    with override_transcription(transcriber=SpyProvider(), mock_fetcher=SpyFetcher()):
        from app.jobs.testing import run_due_jobs

        run_due_jobs(inbox.clock, session_factory=guarded)  # type: ignore[arg-type]
    assert open_during == [("fetch", 0), ("transcribe", 0)]
    row = transcript_of(inbox, "v-1")
    assert row is not None and row.status == "succeeded"


def test_a_duplicate_webhook_and_a_repeated_job_call_the_provider_once(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    deliver_voice(inbox, "price_question_tr", mid="v-1")
    payload = inbox.message_payload(None, attachments=voice(), mid="v-1")
    assert inbox.post(payload).status_code == 200  # the same provider message again
    inbox.process()
    # and the same job run a second time (a lease reclaimed after the first finished)
    message = inbox.messages()[0]
    with inbox.factory() as session:
        enqueue(
            session,
            "transcribe_voice_note",
            TranscribeVoiceNotePayload(message_id=message.id),
            workspace_id=inbox.env.workspace.id,
            correlation_id=None,
            clock=inbox.clock,
        )
        session.commit()
    inbox.process()
    inbox.session.expire_all()
    assert len(inbox.session.scalars(select(MessageTranscript)).all()) == 1
    assert len(fake.calls) == 1  # INV-06: one remote effect


def test_the_daily_quota_per_workspace_stops_further_provider_calls(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    with override_transcription(
        settings=inbox.settings.model_copy(update={"transcription_max_per_workspace_per_day": 1})
    ):
        first = deliver_voice(inbox, "price_question_tr", mid="v-1")
        second = deliver_voice(inbox, "hours_question_tr", mid="v-2", customer="cust-2")
    assert first is not None and first.status == "succeeded"
    assert second is not None and second.reason_code == "VOICE_QUOTA_EXCEEDED"
    assert len(fake.calls) == 1


def test_transcription_can_be_switched_off(inbox: InboxEnv) -> None:
    with override_transcription(
        settings=inbox.settings.model_copy(update={"transcription_provider": "off"})
    ):
        row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is None and transcript_jobs(inbox) == []
    (message,) = inbox.messages()
    assert message.attachments[0]["type"] == "audio"  # still shown as an attachment


def test_an_image_or_text_message_and_a_business_echo_are_not_transcribed(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    inbox.deliver_and_process(None, attachments=[{"type": "image", "url": "https://x.test/a.jpg"}])
    inbox.deliver_and_process("Merhaba", mid="t-1")
    echo = wf.build_echo_payload(
        inbox.account.external_account_id, "cust-1", "echo-1", None, inbox.clock.now()
    )
    echo["entry"][0]["messaging"][0]["message"]["attachments"] = [
        {"type": "audio", "payload": {"url": "mock-audio://price_question_tr"}}
    ]
    assert inbox.post(echo).status_code == 200
    inbox.process()
    inbox.session.expire_all()
    assert inbox.session.scalars(select(MessageTranscript)).all() == []
    assert fake.calls == []


# --- erasure while the provider ran, and afterwards ----------------------------------------------


def test_a_message_deleted_while_the_provider_ran_stores_no_transcript(
    inbox: InboxEnv,
) -> None:
    class DeletingProvider(FakeTranscriptionProvider):
        def transcribe_audio(
            self, clip: AudioClip, *, model: str, timeout_s: float
        ) -> TranscriptionResult:
            with inbox.factory() as session:  # the customer unsends the voice note meanwhile
                for message in session.scalars(select(Message)):
                    message.is_deleted = True
                session.commit()
            return super().transcribe_audio(clip, model=model, timeout_s=timeout_s)

    with override_transcription(transcriber=DeletingProvider()):
        row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None
    assert (row.status, row.reason_code, row.text) == ("failed", "VOICE_SOURCE_GONE", None)


def test_a_provider_delete_event_erases_the_stored_transcript(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    row = deliver_voice(inbox, "price_question_tr", mid="v-1")
    assert row is not None and row.text
    delete_item = {
        "object": "instagram",
        "entry": [
            {
                "id": inbox.account.external_account_id,
                "messaging": [
                    {
                        "sender": {"id": "cust-1"},
                        "recipient": {"id": inbox.account.external_account_id},
                        "timestamp": 2,
                        "message": {"mid": "v-1", "is_deleted": True},
                    }
                ],
            }
        ],
    }
    assert inbox.post(delete_item).status_code == 200
    inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None and row.text is None and row.erased_at == inbox.clock.now()
    assert row.status == "succeeded"  # the fact that it existed is kept, the words are gone


def test_the_data_subject_export_includes_the_transcript_and_erasure_removes_it(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    from app.operations import data_rights

    deliver_voice(inbox, "price_question_tr", mid="v-1")
    conversation = inbox.conversation()
    ctx = inbox.env.ctx(inbox.env.owner)
    exported = data_rights.export_conversation(inbox.session, inbox.clock, ctx, conversation.id)
    (message,) = exported["messages"]
    assert message["transcript"]["text"] == "Merhaba, aylık üyelik ücreti ne kadar acaba?"
    assert message["transcript"]["source"] == "transcript"

    # Since Session 02 the voice note gets a draft at once, so this also covers erasing a
    # conversation that has a stored draft (the draft <-> message links are broken first).
    assert inbox.session.scalars(select(ReplyDraft)).first() is not None
    data_rights.erase_conversation(inbox.session, inbox.clock, ctx, conversation.id)
    inbox.session.commit()
    inbox.session.expire_all()
    assert inbox.session.scalars(select(ReplyDraft)).all() == []
    rows = inbox.session.scalars(select(MessageTranscript)).all()
    assert all(row.text is None and row.erased_at is not None for row in rows)


def test_a_pending_transcript_that_is_erased_never_gets_text_later(
    inbox: InboxEnv, fake: FakeTranscriptionProvider
) -> None:
    from app.inbox import processing
    from app.inbox.transcripts import erase_transcripts

    inbox.deliver(None, attachments=voice(), mid="v-1")
    event = inbox.session.scalars(select(InboundEvent)).one()
    processing.process_inbound_event(  # the message and its pending transcript, but no job run
        inbox.session, inbox.clock, inbox.env.workspace.id, event.id, debounce_seconds=8
    )
    inbox.session.expire_all()
    assert transcript_of(inbox, "v-1").status == "pending"  # type: ignore[union-attr]
    erase_transcripts(
        inbox.session, inbox.clock.now(), MessageTranscript.workspace_id == inbox.env.workspace.id
    )
    inbox.session.commit()
    inbox.process()
    row = transcript_of(inbox, "v-1")
    assert row is not None and (row.status, row.reason_code) == ("failed", "VOICE_SOURCE_GONE")
    assert row.text is None and fake.calls == []


def test_the_default_provider_in_the_test_environment_is_the_offline_fake(
    inbox: InboxEnv,
) -> None:
    assert inbox.settings.transcription_backend == "fake"
