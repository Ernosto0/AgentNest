"""Read a usable-fact snapshot, end the transaction, then draw and store."""

from typing import Literal

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.content import brand, media
from app.content.models import MediaAsset
from app.content.templates.cards import ResolvedCard, render_card
from app.content.templates.spec import (
    LABELS,
    Announcement,
    BrandRecord,
    FactUse,
    HoursCard,
    PriceCard,
    RenderRecord,
    ServicesList,
    TemplateInput,
)
from app.core.clock import Clock
from app.core.config import Settings
from app.core.context import WorkspaceContext
from app.core.errors import AppError
from app.identity.models import Workspace
from app.integrations.storage.base import MediaStorage
from app.knowledge.claims import validate_claims
from app.knowledge.formatting import format_value, weekly_hours_parts
from app.knowledge.render import PLACEHOLDER, RenderResult, placeholder_keys, render
from app.knowledge.service import usable_facts


def prepare(
    db: Session, clock: Clock, ctx: WorkspaceContext, body: TemplateInput
) -> tuple[ResolvedCard, RenderRecord, str | None]:
    workspace = db.scalar(select(Workspace).where(Workspace.id == ctx.workspace_id))
    if workspace is None:
        raise AppError("NOT_FOUND")
    language: Literal["tr", "en"] = body.language or (
        "en" if workspace.default_locale == "en" else "tr"
    )
    facts = usable_facts(db, clock, ctx, locale=language)
    by_key = {f.key: f for f in facts}
    effective = brand.get_brand(db, ctx)
    palette = BrandRecord.model_validate(
        effective.model_dump(include={"primary_color", "accent_color", "logo_media_asset_id"})
    )
    logo_key = (
        media.get_asset(db, ctx, effective.logo_media_asset_id).storage_key
        if effective.logo_media_asset_id
        else None
    )
    keys: list[str] = []
    texts: dict[str, str] = {}
    if isinstance(body, (PriceCard, HoursCard)):
        keys.append(body.fact_key)
    elif isinstance(body, ServicesList):
        keys.extend(body.fact_keys)
    elif isinstance(body, Announcement):
        for field in ("headline", "body", "date_line"):
            value = getattr(body, field)
            if value:
                texts[field] = value
                keys.extend(placeholder_keys(value))
    missing = list(dict.fromkeys(key for key in keys if key not in by_key))
    if missing:
        raise AppError("TEMPLATE_FACT_NOT_USABLE", keys=missing)
    used: dict[str, FactUse] = {}
    for key in keys:
        fact = by_key[key]
        used.setdefault(key, FactUse(fact_id=fact.fact_id, key=key, version=fact.version))
    title = LABELS[body.template][language]
    rows: list[str] = []
    if isinstance(body, Announcement):
        rendered: dict[str, str] = {}
        for field, text in texts.items():
            result = render(text, facts, language)
            # Template free text trusts placeholder spans only. The shared validator also
            # permits copied URLs and discount words beside a promotion in other workflows;
            # scanning the literal portions independently keeps this contract stricter.
            literal = PLACEHOLDER.sub(" ", text)
            if (
                not result.ok
                or not validate_claims(literal, RenderResult(text=literal), language).passed
                or not validate_claims(result.text, result, language).passed
            ):
                raise AppError("TEMPLATE_TEXT_UNGROUNDED", fields=[field])
            rendered[field] = result.text
        title = rendered["headline"]
        rows = [
            rendered["body"] + ("\n" + rendered["date_line"] if "date_line" in rendered else "")
        ]
    else:
        expected = "weekly_hours" if isinstance(body, HoursCard) else "money"
        wrong = list(dict.fromkeys(key for key in keys if by_key[key].value_type != expected))
        if wrong:
            raise AppError(
                "TEMPLATE_FACT_TYPE_MISMATCH", keys=wrong, accepted_value_types=[expected]
            )
        for key in keys:
            fact = by_key[key]
            display = format_value(fact.value_type, fact.value, language)
            label = fact.label.get(language) or fact.label.get("tr") or fact.label.get("en") or key
            if isinstance(body, PriceCard):
                title = label
                rows.append(display)
            elif isinstance(body, HoursCard):
                days, exceptions = weekly_hours_parts(fact.value, language)
                rows.extend([*days, *exceptions])
            else:
                rows.append(f"{label} — {display}")
    card = ResolvedCard(body.template, body.format, title, tuple(rows), workspace.name)
    record = RenderRecord(
        template=body.template,
        format=body.format,
        language=language,
        facts=list(used.values()),
        inputs=body.model_dump(exclude={"template", "format", "language", "fact_key", "fact_keys"}),
        brand=palette,
        rendered_at=clock.now(),
    )
    db.commit()  # end the read snapshot before storage I/O and Pillow work
    return card, record, logo_key


def draw(
    card: ResolvedCard, record: RenderRecord, logo_key: str | None, storage: MediaStorage
) -> bytes:
    logo = None
    if logo_key:
        with storage.open(logo_key) as stream, Image.open(stream) as image:
            logo = image.copy()
    return render_card(card, record.brand, logo)


def preview(
    db: Session,
    clock: Clock,
    settings: Settings,
    storage: MediaStorage,
    ctx: WorkspaceContext,
    body: TemplateInput,
) -> bytes:
    card, record, logo_key = prepare(db, clock, ctx, body)
    raw = draw(card, record, logo_key, storage)
    return media.validate_bytes(db, clock, settings, ctx, raw, None).data


def create(
    db: Session,
    clock: Clock,
    settings: Settings,
    storage: MediaStorage,
    ctx: WorkspaceContext,
    body: TemplateInput,
) -> MediaAsset:
    card, record, logo_key = prepare(db, clock, ctx, body)
    raw = draw(card, record, logo_key, storage)
    return media.ingest_bytes(
        db,
        clock,
        settings,
        storage,
        ctx,
        raw,
        f"template-{body.template}-{body.format}.png",
        render_record=record.model_dump(mode="json"),
    )
