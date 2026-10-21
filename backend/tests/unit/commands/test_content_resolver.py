"""The content reference resolver (agent-runtime.md §3 step 3): alias first, else the local
date (workspace timezone), type and status; none -> REFERENCE_NOT_FOUND, several -> a question.
Pure: no database, no clock, no model."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.ai.schemas import (
    ContentCancelScheduled,
    ContentCreateDraft,
    ContentRef,
    QueryContentStatus,
    QueryExplainFailure,
)
from app.commands import resolver
from app.commands.resolver import ContentContext, ContentSnapshot

TZ = "Europe/Istanbul"  # UTC+3 all year
NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


def item(
    title: str,
    *,
    status: str = "scheduled",
    kind: str = "feed_image",
    at: datetime | None = None,
    version: int = 3,
    updated: datetime | None = None,
    code: str | None = None,
) -> ContentSnapshot:
    return ContentSnapshot(
        id=uuid.uuid4(),
        title=title,
        content_type=kind,
        status=status,
        version=version,
        scheduled_at=at,
        updated_at=updated or NOW,
        last_error_code=code,
    )


def ref(**fields: object) -> ContentRef:
    return ContentRef(
        **{"alias": None, "description": None, "local_date": None, "content_type": None, **fields}  # type: ignore[arg-type]
    )


def context(*items: ContentSnapshot, aliases: dict[str, uuid.UUID] | None = None) -> ContentContext:
    return ContentContext(items, aliases or {}, TZ)


def cancel(r: ContentRef, content: ContentContext) -> resolver.Outcome:
    return resolver.resolve(
        ContentCancelScheduled(type="content.cancel_scheduled", content_ref=r),
        [],
        user_locale="tr",
        workspace_locale="tr",
        currency="TRY",
        content=content,
    )


TOMORROW_EVENING = datetime(2026, 1, 16, 16, 0, tzinfo=UTC)  # 19:00 in Istanbul


def test_an_alias_names_the_item_and_binds_the_cancel_to_its_version() -> None:
    wanted = item("Deneme dersi", at=TOMORROW_EVENING)
    other = item("Haftalık program", at=TOMORROW_EVENING)
    outcome = cancel(ref(alias="c1"), context(other, wanted, aliases={"C1": wanted.id}))
    assert isinstance(outcome, resolver.Confirm)
    assert outcome.command_type == "content.cancel_scheduled"
    assert outcome.action == "command.cancel_content"
    assert outcome.payload == {"content_id": str(wanted.id), "content_version": 3}
    assert outcome.fact_id is None
    assert outcome.summary["label"] == "Deneme dersi" and outcome.summary["when"] == "16 Oca 19:00"


def test_one_match_by_local_date_type_and_status_is_the_item() -> None:
    wanted = item("Yarınki post", at=TOMORROW_EVENING)
    later = item("Haftaya", at=TOMORROW_EVENING + timedelta(days=7))
    done = item("Yayınlandı", status="published", at=TOMORROW_EVENING)
    story = item("Story", kind="story_image", at=TOMORROW_EVENING)
    outcome = cancel(
        ref(local_date="2026-01-16", content_type="feed_image"),
        context(wanted, later, done, story),
    )
    assert isinstance(outcome, resolver.Confirm)
    assert outcome.payload["content_id"] == str(wanted.id)


def test_the_date_is_the_workspace_local_date_not_the_utc_date() -> None:
    late_evening = item("Gece", at=datetime(2026, 1, 16, 21, 30, tzinfo=UTC))  # 00:30 on the 17th
    on_the_16th = cancel(ref(local_date="2026-01-16"), context(late_evening))
    on_the_17th = cancel(ref(local_date="2026-01-17"), context(late_evening))
    assert isinstance(on_the_16th, resolver.Rejected)
    assert isinstance(on_the_17th, resolver.Confirm)


def test_no_match_is_reference_not_found_with_a_link() -> None:
    outcome = cancel(ref(local_date="2026-01-20"), context(item("Başka", at=TOMORROW_EVENING)))
    assert isinstance(outcome, resolver.Rejected)
    assert outcome.error_code == "REFERENCE_NOT_FOUND"
    assert outcome.result.message_key == "command.reference_not_found"
    assert outcome.result.error_code == "REFERENCE_NOT_FOUND"
    assert outcome.result.links == [{"target": "content"}]


def test_an_alias_that_names_nothing_is_not_guessed() -> None:
    outcome = cancel(ref(alias="C9"), context(item("A", at=TOMORROW_EVENING)))
    assert isinstance(outcome, resolver.Rejected) and outcome.error_code == "REFERENCE_NOT_FOUND"


def test_an_unknown_alias_falls_back_to_the_other_filters() -> None:
    wanted = item("A", at=TOMORROW_EVENING)
    outcome = cancel(ref(alias="C9", local_date="2026-01-16"), context(wanted))
    assert isinstance(outcome, resolver.Confirm)


def test_two_matches_are_a_question_with_title_and_time_never_a_guess() -> None:
    morning = item("Sabah postu", at=datetime(2026, 1, 16, 7, 0, tzinfo=UTC))
    evening = item("Akşam postu", at=TOMORROW_EVENING)
    outcome = cancel(ref(local_date="2026-01-16"), context(evening, morning))
    assert isinstance(outcome, resolver.NeedsClarification)
    assert outcome.kind == "content" and outcome.question_key == "command.clarify.which_content"
    assert [o.label for o in outcome.options] == [
        "Sabah postu · 16 Oca 10:00",
        "Akşam postu · 16 Oca 19:00",
    ]
    assert [o.id for o in outcome.options] == ["1", "2"]
    assert outcome.pending == {"intent": "content.cancel_scheduled"}
    assert outcome.options[0].value == {"content_id": str(morning.id)}


def test_a_description_narrows_but_never_empties() -> None:
    trial = item("Deneme dersi duyurusu", at=TOMORROW_EVENING)
    plan = item("Haftalık program", at=TOMORROW_EVENING)
    context_ = context(trial, plan)
    narrowed = cancel(ref(local_date="2026-01-16", description="deneme dersi"), context_)
    assert isinstance(narrowed, resolver.Confirm) and narrowed.payload["content_id"] == str(
        trial.id
    )
    unrelated = cancel(ref(local_date="2026-01-16", description="yaz kampanyası"), context_)
    assert isinstance(unrelated, resolver.NeedsClarification)  # nothing matched: still ambiguous


def test_the_choice_continues_with_the_picked_item_and_nothing_else() -> None:
    a = item("A", at=TOMORROW_EVENING)
    b = item("B", at=TOMORROW_EVENING + timedelta(hours=1), version=7)
    content = context(a, b)
    question = cancel(ref(local_date="2026-01-16"), content)
    assert isinstance(question, resolver.NeedsClarification)
    stored = {
        "kind": question.kind,
        "options": [{"id": o.id, "label": o.label, "value": o.value} for o in question.options],
        "pending": question.pending,
    }
    outcome = resolver.resolve_choice(
        stored, "2", [], user_locale="tr", workspace_locale="tr", currency="TRY", content=content
    )
    assert isinstance(outcome, resolver.Confirm)
    assert outcome.payload == {"content_id": str(b.id), "content_version": 7}
    assert (
        resolver.resolve_choice(
            stored,
            "9",
            [],
            user_locale="tr",
            workspace_locale="tr",
            currency="TRY",
            content=content,
        )
        is None
    )  # a client cannot pick what was never offered
    gone = resolver.resolve_choice(
        stored, "1", [], user_locale="tr", workspace_locale="tr", currency="TRY", content=context()
    )
    assert isinstance(gone, resolver.Rejected) and gone.error_code == "REFERENCE_NOT_FOUND"


@pytest.mark.parametrize("status", ["published", "publishing", "failed", "rejected", "cancelled"])
def test_an_alias_to_something_that_cannot_be_cancelled_is_a_conflict(status: str) -> None:
    named = item("Bitti", status=status, at=TOMORROW_EVENING)
    outcome = cancel(ref(alias="C1"), context(named, aliases={"C1": named.id}))
    assert isinstance(outcome, resolver.Rejected) and outcome.error_code == "CONFLICT_STATE"
    assert outcome.result.message_key == "command.content_not_cancellable"


def test_filters_never_offer_what_cannot_be_cancelled() -> None:
    cancelled_already = item("Eski", status="cancelled", at=TOMORROW_EVENING)
    outcome = cancel(ref(local_date="2026-01-16"), context(cancelled_already))
    assert isinstance(outcome, resolver.Rejected) and outcome.error_code == "REFERENCE_NOT_FOUND"


def test_no_content_at_all_is_not_found() -> None:
    assert isinstance(cancel(ref(), context()), resolver.Rejected)
    assert isinstance(cancel(ref(), None), resolver.Rejected)  # type: ignore[arg-type]


def explain(r: ContentRef | str, content: ContentContext) -> resolver.Outcome:
    return resolver.resolve(
        QueryExplainFailure(type="query.explain_failure", content_ref=r),  # type: ignore[arg-type]
        [],
        user_locale="tr",
        workspace_locale="tr",
        currency="TRY",
        content=content,
    )


def test_latest_failure_is_the_most_recently_changed_problem() -> None:
    old = item("Eski", status="failed", updated=NOW - timedelta(days=3), code="MEDIA_REJECTED")
    new = item("Yeni", status="on_hold", updated=NOW - timedelta(hours=1))
    fine = item("İyi", status="scheduled", updated=NOW)
    outcome = explain("latest_failure", context(old, new, fine))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.command_type == "query.explain_failure"
    assert outcome.resolution == {"content_id": str(new.id)}


def test_latest_failure_with_no_failure_is_an_answer_not_an_error() -> None:
    outcome = explain("latest_failure", context(item("İyi", at=TOMORROW_EVENING)))
    assert isinstance(outcome, resolver.Completed)
    assert outcome.result.message_key == "command.no_failure" and not outcome.result.error_code


def reply_failure(
    when: datetime, code: str | None = "OUTCOME_UNCONFIRMED"
) -> resolver.ReplyFailureSnapshot:
    return resolver.ReplyFailureSnapshot(id=uuid.uuid4(), completed_at=when, error_code=code)


def with_replies(
    *items: ContentSnapshot,
    replies: tuple[resolver.ReplyFailureSnapshot, ...] = (),
    cutoff: datetime | None = None,
) -> ContentContext:
    return ContentContext(items, {}, TZ, reply_failures=replies, failure_cutoff=cutoff)


def test_latest_failure_takes_a_reply_that_failed_after_the_post() -> None:
    post = item("Post", status="failed", updated=NOW - timedelta(hours=3), code="MEDIA_REJECTED")
    older = reply_failure(NOW - timedelta(hours=5))
    newer = reply_failure(NOW - timedelta(hours=1))
    outcome = explain("latest_failure", with_replies(post, replies=(older, newer)))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"operation_id": str(newer.id)}


def test_latest_failure_takes_a_post_that_failed_after_the_reply() -> None:
    post = item("Post", status="failed", updated=NOW - timedelta(minutes=5), code="MEDIA_REJECTED")
    reply = reply_failure(NOW - timedelta(hours=1))
    outcome = explain("latest_failure", with_replies(post, replies=(reply,)))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"content_id": str(post.id)}


def test_a_reply_alone_is_enough_for_latest_failure() -> None:
    reply = reply_failure(NOW)
    outcome = explain("latest_failure", with_replies(replies=(reply,)))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"operation_id": str(reply.id)}


def test_latest_failure_ignores_everything_before_the_cutoff() -> None:
    cutoff = NOW - timedelta(days=7)
    stale_post = item("Eski", status="failed", updated=cutoff - timedelta(minutes=1))
    stale_reply = reply_failure(cutoff - timedelta(minutes=1))
    outcome = explain(
        "latest_failure", with_replies(stale_post, replies=(stale_reply,), cutoff=cutoff)
    )
    assert isinstance(outcome, resolver.Completed)
    assert outcome.result.message_key == "command.no_failure"

    edge = reply_failure(cutoff)  # exactly at the cutoff still counts
    outcome = explain("latest_failure", with_replies(stale_post, replies=(edge,), cutoff=cutoff))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"operation_id": str(edge.id)}


def test_a_named_post_never_resolves_to_a_reply() -> None:
    failed = item("Bozuk", status="failed", at=TOMORROW_EVENING, code="PUBLISH_DEADLINE_PASSED")
    reply = reply_failure(NOW)
    outcome = explain(ref(local_date="2026-01-16"), with_replies(failed, replies=(reply,)))
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"content_id": str(failed.id)}


def test_explain_by_reference_only_considers_posts_in_trouble() -> None:
    failed = item("Bozuk", status="failed", at=TOMORROW_EVENING, code="PUBLISH_DEADLINE_PASSED")
    fine = item("İyi", status="scheduled", at=TOMORROW_EVENING)
    outcome = explain(ref(local_date="2026-01-16"), context(failed, fine))
    assert isinstance(outcome, resolver.Execute) and outcome.resolution["content_id"] == str(
        failed.id
    )


def test_status_lookup_ignores_cancelled_but_not_the_rest() -> None:
    live = item("Canlı", at=TOMORROW_EVENING)
    gone = item("İptal", status="cancelled", at=TOMORROW_EVENING)
    outcome = resolver.resolve(
        QueryContentStatus(type="query.content_status", content_ref=ref(local_date="2026-01-16")),
        [],
        user_locale="tr",
        workspace_locale="tr",
        currency="TRY",
        content=context(live, gone),
    )
    assert isinstance(outcome, resolver.Execute)
    assert outcome.resolution == {"content_id": str(live.id)}


def test_create_draft_needs_an_objective() -> None:
    def create(objective: str, notes: str | None = None) -> resolver.Outcome:
        return resolver.resolve(
            ContentCreateDraft(
                type="content.create_draft",
                content_type="story_image",
                objective=objective,
                notes=notes,
            ),
            [],
            user_locale="tr",
            workspace_locale="tr",
            currency="TRY",
        )

    ok = create("  Deneme dersi  ", " ")
    assert isinstance(ok, resolver.Execute)
    assert ok.resolution == {
        "content_type": "story_image",
        "objective": "Deneme dersi",
        "notes": None,
    }
    blank = create("   ")
    assert isinstance(blank, resolver.Rejected) and blank.error_code == "VALIDATION_FAILED"
