"""Explicit price-card decisions stage DB-only drafts; workers attach images later."""

import uuid
from dataclasses import replace

import pytest
from sqlalchemy import select

from app.approvals.models import Approval
from app.audit.models import AuditLog
from app.commands.models import OwnerCommand
from app.content.models import ContentItem, MediaAsset
from app.content.payload import RenderTemplateImagePayload
from app.content.templates.jobs import render_template_image
from app.core.config import get_settings
from app.jobs.models import Job
from app.jobs.registry import JobContext
from app.knowledge import service as knowledge
from app.knowledge.models import FactReference
from tests.factories import create_workspace, money
from tests.integration.commands.conftest import MONTHLY, CommandEnv

TEXT = "aylik uyelik icin fiyat karti yap"


def job_context(cmd, job):
    return JobContext(
        job.id,
        job.job_type,
        job.workspace_id,
        None,
        RenderTemplateImagePayload.model_validate(job.payload),
        1,
        3,
        cmd.factory,
        cmd.env.clock,
        lambda: None,
    )


def staged(cmd, role=None):
    command = cmd.run(role or cmd.env.owner, TEXT)
    assert command["status"] == "awaiting_confirmation", command
    assert command["approval"]["action"] == "command.make_price_card"
    assert "6.000" in command["approval"]["summary"]["price_formatted"]
    assert not cmd.env.session.scalars(select(ContentItem)).all()
    decision = cmd.decide(role or cmd.env.owner, command["approval"])
    assert decision.status_code == 200, decision.text
    cmd.env.session.expire_all()
    item = cmd.env.session.scalars(select(ContentItem)).one()
    assert item.status == "draft" and item.version == 1 and item.media_asset_id is None
    job = cmd.env.session.scalars(select(Job).where(Job.job_type == "render_template_image")).one()
    assert job.status == "queued" and job.dedup_key == f"render_template_image:{item.id}"
    assert "6000" not in str(job.payload)
    return command, item, job


@pytest.fixture(autouse=True)
def render_settings(monkeypatch, tmp_path):
    settings = get_settings().model_copy(update={"media_local_root": str(tmp_path / "media")})
    monkeypatch.setattr("app.content.templates.jobs.get_settings", lambda: settings)


@pytest.mark.parametrize("role", ["owner", "staff"])
def test_confirmation_then_job_attaches_draft_only(cmd: CommandEnv, role):
    command, item, job = staged(cmd, getattr(cmd.env, role))
    assert cmd.decide(getattr(cmd.env, role), command["approval"]).status_code == 409
    run = job_context(cmd, job)
    render_template_image(run)
    cmd.env.session.expire_all()
    assert item.version == 2 and item.status == "draft" and item.media_asset_id
    assert item.approval_id is None and item.scheduled_at is None and item.published_at is None
    refs = cmd.env.session.scalars(
        select(FactReference).where(FactReference.referrer_id == item.id)
    ).all()
    assert [(r.fact_id, r.fact_version) for r in refs] == [(cmd.facts[MONTHLY].id, 1)]
    assert len(cmd.env.session.scalars(select(MediaAsset)).all()) == 1
    render_template_image(run)
    cmd.env.session.expire_all()
    assert item.version == 2 and len(cmd.env.session.scalars(select(MediaAsset)).all()) == 1
    assert len(cmd.env.session.scalars(select(Approval)).all()) == 1
    if role == "staff":
        response = cmd.env.call(
            cmd.env.staff,
            "POST",
            f"/content-items/{item.id}/submit",
            json={"expected_version": 2, "schedule": "now", "self_approve": True},
        )
        assert response.status_code == 403


def test_fact_changed_between_card_and_decision_creates_nothing(cmd: CommandEnv):
    command = cmd.run(cmd.env.owner, TEXT)
    knowledge.update_fact(
        cmd.env.session,
        cmd.env.clock,
        cmd.env.ctx(cmd.env.owner),
        cmd.facts[MONTHLY].id,
        expected_version=1,
        value=money("7000"),
    )
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    result = cmd.get(cmd.env.owner, command["id"])
    assert result["error_code"] == "FACT_CHANGED_MEANWHILE"
    assert not cmd.env.session.scalars(select(ContentItem)).all()


def test_unverified_price_is_refused(cmd: CommandEnv):
    command = cmd.run(cmd.env.owner, "ogrenci aylik uyelik icin fiyat karti yap")
    assert command["error_code"] == "TEMPLATE_FACT_NOT_USABLE"
    assert command["approval"] is None


def test_clarification_keeps_format_and_hash_binding(cmd: CommandEnv):
    command = cmd.run(cmd.env.owner, "feed fiyat karti yap")
    assert command["status"] == "needs_clarification"
    choice = command["clarification"]["options"][0]["id"]
    response = cmd.env.call(
        cmd.env.owner,
        "POST",
        f"/commands/{command['id']}/clarification",
        json={"option_id": choice},
    )
    assert response.status_code == 202, response.text
    result = cmd.get(cmd.env.owner, command["id"])
    assert result["approval"]["summary"]["format"] == "feed"
    assert cmd.decide(cmd.env.owner, result["approval"], payload_hash="0" * 64).status_code == 409
    row = cmd.env.session.get(OwnerCommand, uuid.UUID(command["id"]))
    assert row.resolution["format"] == "feed"


@pytest.mark.parametrize("changed", ["version", "media", "status", "foreign"])
def test_job_does_not_overwrite_owner_or_foreign_draft(cmd: CommandEnv, changed):
    _, item, job = staged(cmd)
    run = job_context(cmd, job)
    if changed == "version":
        item.version += 1
    elif changed == "status":
        item.status = "cancelled"
    elif changed == "foreign":
        workspace = create_workspace(cmd.env.session)
        run = replace(run, workspace_id=workspace.id)
    else:
        from tests.helpers.content import make_media

        item.media_asset_id = make_media(cmd.env).id
    cmd.env.session.commit()
    before = item.media_asset_id
    render_template_image(run)
    cmd.env.session.expire_all()
    assert item.media_asset_id == before
    assert not cmd.env.session.scalars(
        select(MediaAsset).where(MediaAsset.render_record.is_not(None))
    ).all()


def test_fact_becoming_unusable_before_render_is_terminal(cmd: CommandEnv):
    _, item, job = staged(cmd)
    fact = cmd.facts[MONTHLY]
    fact.status = "unverified"
    cmd.env.session.commit()
    render_template_image(job_context(cmd, job))
    cmd.env.session.expire_all()
    assert item.status == "draft" and item.media_asset_id is None and item.version == 1
    log = cmd.env.session.scalars(
        select(AuditLog).where(AuditLog.action == "content.template_image_failed")
    ).one()
    assert log.metadata_ == {"code": "TEMPLATE_FACT_NOT_USABLE"}


def test_fact_unverified_after_card_refuses_without_draft(cmd: CommandEnv):
    command = cmd.run(cmd.env.owner, TEXT)
    cmd.facts[MONTHLY].status = "unverified"
    cmd.env.session.commit()
    assert cmd.decide(cmd.env.owner, command["approval"]).status_code == 200
    assert cmd.get(cmd.env.owner, command["id"])["error_code"] == "TEMPLATE_FACT_NOT_USABLE"
    assert not cmd.env.session.scalars(select(ContentItem)).all()


def test_owner_edit_during_render_discards_asset(cmd: CommandEnv, monkeypatch):
    from app.content.templates import service

    _, item, job = staged(cmd)
    original = service.draw
    original_prepare = service.prepare
    rendering_sessions = []

    def preparing(db, clock, ctx, body):
        rendering_sessions.append(db)
        return original_prepare(db, clock, ctx, body)

    monkeypatch.setattr(service, "prepare", preparing)

    def edited(card, record, logo_key, storage):
        # Renderer service ended its snapshot before entering Pillow/storage.
        assert not rendering_sessions[0].in_transaction()
        raw = original(card, record, logo_key, storage)
        item.version = 2
        cmd.env.session.commit()
        return raw

    monkeypatch.setattr(service, "draw", edited)
    render_template_image(job_context(cmd, job))
    cmd.env.session.expire_all()
    assert item.media_asset_id is None and item.status == "draft" and item.version == 2
    assert len(cmd.env.session.scalars(select(MediaAsset)).all()) == 1  # orphan cleanup
    log = cmd.env.session.scalars(
        select(AuditLog).where(AuditLog.action == "content.template_image_failed")
    ).one()
    assert log.metadata_ == {"code": "VERSION_CONFLICT"}
