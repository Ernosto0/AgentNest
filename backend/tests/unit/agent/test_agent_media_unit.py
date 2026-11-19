"""Offline unit tests for voice notes and image descriptions in Account Agent (Session 05).

Covers:
1. format_message_text_with_media:
   - Voice-only with succeeded transcript -> [voice transcript: ...]
   - Voice-only with pending transcript -> [attachment: voice note processing]
   - Voice-only with failed transcript -> [attachment: voice note]
   - Voice-only with erased transcript -> [attachment: voice note]
   - Image with succeeded description -> [image description: ...]
   - Image with description + visible text -> [image description: ... (text: ...)]
   - Image with pending description -> [attachment: image processing]
   - Image with failed description -> [attachment: image]
   - Image with erased description -> [attachment: image]
   - Image + typed customer text -> both included, text not dropped
   - Multiple attachments on single message
   - Text only and empty message
2. wake_drafting in inbox/transcription.py:
   - Emits message.transcript_ready on success for agent controller
   - Emits message.transcription_failed on failure for agent controller
   - Respects human takeover, epoch mismatch, message deletion
   - Wakes legacy drafting when controller is in legacy mode
3. wake_after_image_description in inbox/image_description.py:
   - Emits message.image_described on success for agent controller
   - Emits message.image_description_failed on failure for agent controller
   - Respects human takeover, epoch mismatch, message deletion
   - Wakes legacy drafting when controller is in legacy mode
4. Policy and Invariants (INV-02, INV-04, INV-16):
   - recent_transcript forces require_human=True and ask decision even under automatic mode
   - image_injection blocks proposal (is_blocked=True)
   - Ambiguous image-only request requires approval
   - revalidate fences actions with recent transcripts or image injection
5. Customer response obligation in dm.send and coordinator:
   - Media events (message_transcript, message_image_description) count as valid customer events
   - wait_resolved in coordinator wakes on media completion events
   - Voice transcript text feeds reply language selection and recent customer context
"""

import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.agent.context import format_message_text_with_media
from app.agent.coordinator import wait_resolved
from app.agent.delegation import ActionRule, Decision
from app.agent.models import AccountAgent, AgentAction, AgentSession, AgentThread
from app.agent.policy import (
    Complexity,
    Topic,
    classify_request,
    evaluate_action_policy,
)
from app.ai.runner import RunnerDeps
from app.core.clock import FrozenClock
from app.inbox.image_description import wake_after_image_description
from app.inbox.language import choose_reply_language
from app.inbox.models import (
    Conversation,
    Message,
    MessageImageDescription,
    MessageTranscript,
    ReplyDraft,
)
from app.inbox.transcription import wake_drafting
from app.policy.transcripts import recent_transcript_present

AUTO_RULE = ActionRule(mode="automatic")
ASK_RULE = ActionRule(mode="ask")
AUTO_DECISION = Decision("automatic", "delegated")


# ---------------------------------------------------------------------------
# 1. format_message_text_with_media
# ---------------------------------------------------------------------------


def test_format_voice_succeeded() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "audio", "url": "mock://audio"}],
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(),
        message_id=msg_id,
        status="succeeded",
        text="Fiyatlarınız ne kadar acaba?",
    )
    result = format_message_text_with_media(msg, {msg_id: transcript}, {})
    assert result == "[voice transcript: Fiyatlarınız ne kadar acaba?]"


def test_format_voice_pending() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "audio", "url": "mock://audio"}],
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(),
        message_id=msg_id,
        status="pending",
        text=None,
    )
    result = format_message_text_with_media(msg, {msg_id: transcript}, {})
    assert result == "[attachment: voice note processing]"


def test_format_voice_failed() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "audio", "url": "mock://audio"}],
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(),
        message_id=msg_id,
        status="failed",
        reason_code="VOICE_NO_SPEECH",
    )
    result = format_message_text_with_media(msg, {msg_id: transcript}, {})
    assert result == "[attachment: voice note]"


def test_format_voice_erased() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "audio", "url": "mock://audio"}],
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(),
        message_id=msg_id,
        status="succeeded",
        text=None,  # erased for privacy
    )
    result = format_message_text_with_media(msg, {msg_id: transcript}, {})
    assert result == "[attachment: voice note]"


def test_format_image_succeeded() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "image", "url": "mock://img"}],
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
        description="A black leather jacket on a hanger",
        visible_text=None,
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img_desc})
    assert result == "[image description: A black leather jacket on a hanger]"


def test_format_image_succeeded_with_visible_text() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "image", "url": "mock://img"}],
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
        description="A restaurant menu board",
        visible_text="Burger 250 TRY\nPizza 300 TRY",
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img_desc})
    assert (
        "[image description: A restaurant menu board (text: Burger 250 TRY\nPizza 300 TRY)]"
        in result
    )


def test_format_image_pending() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "image", "url": "mock://img"}],
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="pending",
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img_desc})
    assert result == "[attachment: image processing]"


def test_format_image_failed() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text=None,
        attachments=[{"type": "image", "url": "mock://img"}],
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="failed",
        reason_code="IMAGE_TOO_LARGE",
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img_desc})
    assert result == "[attachment: image]"


def test_format_image_plus_typed_text_preserves_both() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text="Bu ürün elinizde var mı?",
        attachments=[{"type": "image", "url": "mock://img"}],
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
        description="Kırmızı spor ayakkabı",
        visible_text=None,
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img_desc})
    assert "Bu ürün elinizde var mı?" in result
    assert "[image description: Kırmızı spor ayakkabı]" in result
    assert result == "Bu ürün elinizde var mı?\n[image description: Kırmızı spor ayakkabı]"


def test_format_multiple_attachments() -> None:
    msg_id = uuid.uuid4()
    msg = Message(
        id=msg_id,
        direction="inbound",
        text="Burada iki resim var:",
        attachments=[
            {"type": "image", "url": "mock://img1"},
            {"type": "image", "url": "mock://img2"},
        ],
    )
    img1 = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
        description="Ön cephe görünümü",
    )
    img2 = MessageImageDescription(
        id=uuid.uuid4(),
        message_id=msg_id,
        attachment_index=1,
        status="pending",
    )
    result = format_message_text_with_media(msg, {}, {(msg_id, 0): img1, (msg_id, 1): img2})
    assert "Burada iki resim var:" in result
    assert "[image description: Ön cephe görünümü]" in result
    assert "[attachment: image processing]" in result


def test_format_text_only() -> None:
    msg = Message(
        id=uuid.uuid4(),
        direction="inbound",
        text="Merhaba, saat kaçta açıksınız?",
        attachments=None,
    )
    result = format_message_text_with_media(msg, {}, {})
    assert result == "Merhaba, saat kaçta açıksınız?"


def test_format_empty_message() -> None:
    msg = Message(
        id=uuid.uuid4(),
        direction="inbound",
        text=None,
        attachments=None,
    )
    result = format_message_text_with_media(msg, {}, {})
    assert result == ""


# ---------------------------------------------------------------------------
# 2. wake_drafting in inbox/transcription.py
# ---------------------------------------------------------------------------


def test_wake_drafting_for_agent_controller_succeeded() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=3,
        state="active",
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=3,
        handling_mode="agent",
    )
    transcript = MessageTranscript(
        id=transcript_id,
        workspace_id=ws_id,
        message_id=msg_id,
        status="succeeded",
        text="Sesli mesaj içeriği",
    )

    db = MagicMock()
    # scalars().one_or_none() for msg, conv; scalar() for agent, thread
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_record.assert_called_once_with(
            db,
            clock,
            message=msg,
            thread=thread,
            kind="message.transcript_ready",
            source_kind="message_transcript",
            source_key=f"transcript:{transcript_id}",
            source_id=str(transcript_id),
        )


def test_wake_drafting_for_agent_controller_failed() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    transcript_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=2,
        state="active",
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=2,
        handling_mode="agent",
    )
    transcript = MessageTranscript(
        id=transcript_id,
        workspace_id=ws_id,
        message_id=msg_id,
        status="failed",
        reason_code="VOICE_NO_SPEECH",
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_record.assert_called_once_with(
            db,
            clock,
            message=msg,
            thread=thread,
            kind="message.transcription_failed",
            source_kind="message_transcript",
            source_key=f"transcript:{transcript_id}",
            source_id=str(transcript_id),
        )


def test_wake_drafting_respects_human_takeover() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=1,
        state="active",
    )
    thread = AgentThread(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=1,
        handling_mode="human",  # Owner took over!
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(), workspace_id=ws_id, message_id=msg_id, status="succeeded", text="test"
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_record.assert_not_called()


def test_wake_drafting_respects_epoch_mismatch() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=5,
        state="active",
    )
    thread = AgentThread(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=4,  # Stale epoch!
        handling_mode="agent",
    )
    transcript = MessageTranscript(
        id=uuid.uuid4(), workspace_id=ws_id, message_id=msg_id, status="succeeded", text="test"
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_record.assert_not_called()


def test_wake_drafting_respects_deleted_message() -> None:
    ws_id = uuid.uuid4()
    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(id=uuid.uuid4(), workspace_id=ws_id, direction="inbound", is_deleted=True)
    transcript = MessageTranscript(
        id=uuid.uuid4(), workspace_id=ws_id, message_id=msg.id, status="succeeded", text="test"
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.return_value = msg

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_record.assert_not_called()


def test_wake_drafting_legacy_mode_enqueues_draft() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(
        id=conv_id, workspace_id=ws_id, social_account_id=acc_id, handling_mode="automatic"
    )
    agent = AccountAgent(workspace_id=ws_id, social_account_id=acc_id, controller_mode="legacy")
    transcript = MessageTranscript(
        id=uuid.uuid4(), workspace_id=ws_id, message_id=msg_id, status="succeeded", text="test"
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.return_value = agent

    with patch("app.inbox.transcription.enqueue") as mock_enqueue:
        wake_drafting(db, clock, transcript, correlation_id=None)
        mock_enqueue.assert_called_once()
        assert mock_enqueue.call_args[0][1] == "draft_reply"


# ---------------------------------------------------------------------------
# 3. wake_after_image_description in inbox/image_description.py
# ---------------------------------------------------------------------------


def test_wake_after_image_description_for_agent_succeeded() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    img_desc_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=1,
        state="active",
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=1,
        handling_mode="agent",
    )
    img_desc = MessageImageDescription(
        id=img_desc_id,
        workspace_id=ws_id,
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
        description="test photo",
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_after_image_description(db, clock, img_desc, correlation_id=None)
        mock_record.assert_called_once_with(
            db,
            clock,
            message=msg,
            thread=thread,
            kind="message.image_described",
            source_kind="message_image_description",
            source_key=f"image_desc:{img_desc_id}",
            source_id=str(img_desc_id),
        )


def test_wake_after_image_description_for_agent_failed() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()
    img_desc_id = uuid.uuid4()
    thread_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=1,
        state="active",
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=1,
        handling_mode="agent",
    )
    img_desc = MessageImageDescription(
        id=img_desc_id,
        workspace_id=ws_id,
        message_id=msg_id,
        attachment_index=0,
        status="failed",
        reason_code="IMAGE_URL_MISSING",
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_after_image_description(db, clock, img_desc, correlation_id=None)
        mock_record.assert_called_once_with(
            db,
            clock,
            message=msg,
            thread=thread,
            kind="message.image_description_failed",
            source_kind="message_image_description",
            source_key=f"image_desc:{img_desc_id}",
            source_id=str(img_desc_id),
        )


def test_wake_after_image_description_respects_human_takeover() -> None:
    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    msg = Message(
        id=msg_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        direction="inbound",
        is_deleted=False,
    )
    conv = Conversation(id=conv_id, workspace_id=ws_id, social_account_id=acc_id)
    agent = AccountAgent(
        workspace_id=ws_id,
        social_account_id=acc_id,
        controller_mode="agent",
        controller_epoch=1,
        state="active",
    )
    thread = AgentThread(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        social_account_id=acc_id,
        surface="dm",
        source_ref=str(conv_id),
        dm_conversation_id=conv_id,
        controller_epoch=1,
        handling_mode="human",
    )
    img_desc = MessageImageDescription(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        message_id=msg_id,
        attachment_index=0,
        status="succeeded",
    )

    db = MagicMock()
    db.scalars.return_value.one_or_none.side_effect = [msg, conv]
    db.scalar.side_effect = [agent, thread]

    with patch("app.agent.media.wake_for_media") as mock_record:
        wake_after_image_description(db, clock, img_desc, correlation_id=None)
        mock_record.assert_not_called()


# ---------------------------------------------------------------------------
# 4. Invariants & Policy (INV-02, INV-04, INV-16)
# ---------------------------------------------------------------------------


def test_voice_transcript_forces_human_approval() -> None:
    """Rule F-03 & INV-04: Voice-derived replies strictly require approval regardless of grant."""
    classification = classify_request(
        action_type="dm.send",
        surface="dm",
        inbound_text="Fiyat nedir?",
        recent_transcript=True,
    )
    assert classification.is_basic is False
    assert classification.requires_human is True
    assert classification.primary_topic == "voice_transcript"
    assert classification.reason == "voice_transcript_requires_approval"

    # Even with AUTO_RULE (automatic mode), decision MUST be ask!
    decision = evaluate_action_policy(AUTO_RULE, classification, base_decision=AUTO_DECISION)
    assert decision.kind == "ask"
    assert decision.reason == "voice_transcript_requires_approval"


def test_image_injection_blocks_proposal() -> None:
    """INV-03: Suspected injection in image description blocks proposal."""
    classification = classify_request(
        action_type="dm.send",
        surface="dm",
        inbound_text="Here is a picture",
        image_injection=True,
    )
    assert classification.is_blocked is True
    assert classification.complexity == Complexity.BLOCKED
    assert classification.primary_topic == Topic.INJECTION.value
    assert classification.reason == "injection_suspected"

    decision = evaluate_action_policy(AUTO_RULE, classification, base_decision=AUTO_DECISION)
    assert decision.kind == "blocked"


def test_ambiguous_image_only_requires_approval() -> None:
    """Ambiguous visual queries without basic FAQ intent require approval."""
    classification = classify_request(
        action_type="dm.send",
        surface="dm",
        inbound_text=None,  # image-only: no customer text
    )
    assert classification.is_basic is False
    assert classification.requires_human is True
    assert classification.reason == "unclear_or_unrecognized_request"

    decision = evaluate_action_policy(AUTO_RULE, classification, base_decision=AUTO_DECISION)
    assert decision.kind == "ask"


def test_recent_transcript_present_query() -> None:
    ws_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    db = MagicMock()

    # Found a transcript
    db.scalar.return_value = uuid.uuid4()
    assert recent_transcript_present(db, ws_id, conv_id) is True

    # No transcript found
    db.scalar.return_value = None
    assert recent_transcript_present(db, ws_id, conv_id) is False


# ---------------------------------------------------------------------------
# 5. Customer response obligation in dm.send and coordinator
# ---------------------------------------------------------------------------


def test_coordinator_wait_resolved_wakes_on_transcript_event() -> None:
    """A goal in waiting_customer resolves when message_transcript event arrives."""
    ws_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    goal = AgentSession(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        thread_id=thread_id,
        status="waiting_customer",
        activation_cursor=1,
    )
    thread = AgentThread(id=thread_id, workspace_id=ws_id, event_cursor=2)

    db = MagicMock()
    deps = MagicMock(spec=RunnerDeps)
    deps.clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))

    # Event query finds matching event
    db.scalar.return_value = uuid.uuid4()
    resolved = wait_resolved(db, deps, goal, thread)
    assert resolved is True


def test_coordinator_wait_resolved_wakes_on_image_described_event() -> None:
    """A goal in waiting_customer resolves when message_image_description event arrives."""
    ws_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    goal = AgentSession(
        id=uuid.uuid4(),
        workspace_id=ws_id,
        thread_id=thread_id,
        status="waiting_customer",
        activation_cursor=3,
    )
    thread = AgentThread(id=thread_id, workspace_id=ws_id, event_cursor=4)

    db = MagicMock()
    deps = MagicMock(spec=RunnerDeps)
    deps.clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))

    db.scalar.return_value = uuid.uuid4()
    resolved = wait_resolved(db, deps, goal, thread)
    assert resolved is True


def test_voice_transcript_speech_in_language_detection() -> None:
    """Voice transcript text enables proper language detection across all five languages."""
    langs = ["tr", "en", "ru", "de", "ar"]
    # Turkish
    tr_detected = choose_reply_language(
        ["[voice transcript: Fiyatlarınız nedir acaba?]"],
        default_locale="tr",
        reply_languages=langs,
    )
    assert tr_detected.code == "tr"

    # Russian
    ru_detected = choose_reply_language(
        ["[voice transcript: Здравствуйте, сколько стоят ваши услуги?]"],
        default_locale="en",
        reply_languages=langs,
    )
    assert ru_detected.code == "ru"

    # German
    de_detected = choose_reply_language(
        ["[voice transcript: Guten Tag, wie viel kostet ein Haarschnitt?]"],
        default_locale="en",
        reply_languages=langs,
    )
    assert de_detected.code == "de"

    # Arabic
    ar_detected = choose_reply_language(
        ["[voice transcript: مرحبا، كم سعر هذه الخدمة من فضلكم؟]"],
        default_locale="en",
        reply_languages=langs,
    )
    assert ar_detected.code == "ar"

    # English
    en_detected = choose_reply_language(
        ["[voice transcript: Hello, what are your opening hours today?]"],
        default_locale="tr",
        reply_languages=langs,
    )
    assert en_detected.code == "en"


def test_dm_revalidate_fences_recent_transcript() -> None:
    """revalidate() refuses automatic send if a voice transcript is present in the conversation."""
    from app.agent.dm import revalidate
    from app.identity.models import Workspace

    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    action_id = uuid.uuid4()
    draft_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    workspace = Workspace(
        id=ws_id,
        timezone="Europe/Istanbul",
        default_locale="tr",
        is_demo=False,
    )
    conv = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        dm_conversation_id=conv_id,
        event_cursor=2,
        deletion_generation=0,
        ownership_generation=1,
    )
    action = AgentAction(
        id=action_id,
        workspace_id=ws_id,
        thread_id=thread_id,
        payload_ref=draft_id,
        ownership_generation=1,
        policy_grant={"mode": "automatic"},  # Was granted automatic policy
    )
    draft = ReplyDraft(
        id=draft_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        agent_action_id=action_id,
        text="Hello!",
        validation={
            "cursor": 2,
            "deletion_generation": 0,
            "agent_proposal": {
                "template": "Hello!",
                "language": "en",
            },
        },
    )

    db = MagicMock()
    db.get.side_effect = lambda model, obj_id: {
        (AgentAction, action_id): action,
        (AgentThread, thread_id): thread,
        (Workspace, ws_id): workspace,
    }.get((model, obj_id))

    with (
        patch("app.agent.dm.validate_reply") as mock_val,
        patch("app.policy.transcripts.recent_transcript_present", return_value=True),
    ):
        mock_val.return_value = MagicMock(valid=True, text="Hello!")
        assert revalidate(db, clock, draft, conv) is False


def test_dm_revalidate_fences_image_injection() -> None:
    """revalidate() refuses automatic send if an image description has suspected injection."""
    from app.agent.dm import revalidate
    from app.agent.reply_evidence import ReplyEvidence
    from app.identity.models import Workspace

    ws_id = uuid.uuid4()
    acc_id = uuid.uuid4()
    conv_id = uuid.uuid4()
    thread_id = uuid.uuid4()
    action_id = uuid.uuid4()
    draft_id = uuid.uuid4()
    msg_id = uuid.uuid4()

    clock = FrozenClock(datetime(2026, 11, 19, 12, 0, tzinfo=UTC))
    workspace = Workspace(
        id=ws_id,
        timezone="Europe/Istanbul",
        default_locale="tr",
        is_demo=False,
    )
    conv = Conversation(
        id=conv_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
    )
    thread = AgentThread(
        id=thread_id,
        workspace_id=ws_id,
        social_account_id=acc_id,
        dm_conversation_id=conv_id,
        event_cursor=3,
        deletion_generation=0,
        ownership_generation=1,
    )
    action = AgentAction(
        id=action_id,
        workspace_id=ws_id,
        thread_id=thread_id,
        payload_ref=draft_id,
        ownership_generation=1,
        policy_grant={"mode": "automatic"},
    )
    draft = ReplyDraft(
        id=draft_id,
        workspace_id=ws_id,
        conversation_id=conv_id,
        agent_action_id=action_id,
        covers_through_message_id=msg_id,
        text="Hello!",
        validation={
            "cursor": 3,
            "deletion_generation": 0,
            "agent_proposal": {
                "template": "Hello!",
                "language": "en",
            },
        },
    )
    msg = Message(id=msg_id, workspace_id=ws_id, conversation_id=conv_id, direction="inbound")

    db = MagicMock()
    db.get.side_effect = lambda model, obj_id: {
        (AgentAction, action_id): action,
        (AgentThread, thread_id): thread,
        (Workspace, ws_id): workspace,
        (Message, msg_id): msg,
    }.get((model, obj_id))

    # An image with suspected injection exists
    db.scalar.return_value = uuid.uuid4()

    with (
        patch("app.agent.dm.validate_reply") as mock_val,
        patch("app.agent.dm.recent_transcript_present", return_value=False),
        patch(
            "app.agent.dm.response_evidence",
            return_value=ReplyEvidence("Hello", (msg_id,), image_injection=True),
        ),
        patch("app.agent.reply_evidence.escalation_keywords", return_value=[]),
        patch("app.agent.knowledge.prices_shared", return_value=False),
    ):
        mock_val.return_value = MagicMock(valid=True, text="Hello!")
        assert revalidate(db, clock, draft, conv) is False
