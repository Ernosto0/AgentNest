"""Exact business provenance and narrowly attributed customer clarification.

Customer evidence can produce only server-written date/time questions. It cannot mask
an arbitrary model span, authorize an effect or make a business availability promise.
"""

import re
import uuid
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.knowledge import as_usable, visible_predicate
from app.agent.repository import scoped_thread
from app.agent.tools.broker import BrokerContext
from app.core.clock import Clock
from app.inbox.models import Message
from app.knowledge.claims import length_issue, validate_claims
from app.knowledge.models import BusinessFact
from app.knowledge.render import RenderResult, placeholder_keys, render


class FactEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    version: int = Field(ge=1)


class CustomerClarification(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message_id: uuid.UUID
    start: int = Field(ge=0, le=10000)
    end: int = Field(ge=1, le=10000)
    kind: Literal["date", "time"]


class OwnerAnswerEvidence(BaseModel):
    """A persisted private OwnerAnswer reference, never a BusinessFact reference."""

    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    version: int = Field(ge=1)


class ReplyValidationArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    template: str = Field(max_length=900)
    language: Literal["tr", "en"]
    fact_sources: list[FactEvidence] = Field(default_factory=list, max_length=20)
    customer_clarification: CustomerClarification | None = None
    owner_answer: OwnerAnswerEvidence | None = None


@dataclass(frozen=True)
class GroundedReply:
    text: str = ""
    facts: tuple[tuple[uuid.UUID, int], ...] = ()
    customer_source: uuid.UUID | None = None
    errors: tuple[str, ...] = field(default=())

    @property
    def valid(self) -> bool:
        return not self.errors


_DATE = re.compile(r"(?:\d{4}-\d{2}-\d{2}|\d{1,2}[./]\d{1,2}(?:[./]\d{2,4})?)")
_TIME = re.compile(r"(?:[01]?\d|2[0-3]):[0-5]\d")


def validate_reply(
    db: Session,
    clock: Clock,
    context: BrokerContext,
    proposal: ReplyValidationArgs,
) -> GroundedReply:
    thread = scoped_thread(
        db,
        context.workspace.workspace_id,
        context.account_id,
        context.thread_id,
    )
    if thread.surface != context.surface:
        return GroundedReply(errors=("SOURCE_SCOPE_INVALID",))
    from app.agent.context import assemble

    if assemble(db, clock, context).language != proposal.language:
        return GroundedReply(errors=("REPLY_LANGUAGE_MISMATCH",))
    if proposal.owner_answer is not None:
        from app.owner_requests.service import evidence as owner_evidence

        owner_source = proposal.owner_answer
        if proposal.template.strip() or proposal.fact_sources or proposal.customer_clarification:
            return GroundedReply(errors=("OWNER_ATTRIBUTION_INVALID",))
        resolved = owner_evidence(db, clock, context, owner_source.id, owner_source.version)
        if resolved is None:
            return GroundedReply(errors=("OWNER_SOURCE_INVALID",))
        _, answer, _ = resolved
        # Entire reply is server-rendered. No arbitrary numeric/span exemption and
        # no owner answer ID is ever offered to business-fact render/claim validation.
        owner_text = (
            f"İşletmenin bu talebinize yanıtı: {answer.body}"
            if proposal.language == "tr"
            else f"The business's answer to your request: {answer.body}"
        )
        if length_issue(owner_text, max_bytes=1000):
            return GroundedReply(errors=("REPLY_LENGTH_INVALID",))
        return GroundedReply(owner_text)
    if proposal.customer_clarification is not None:
        source = proposal.customer_clarification
        # No model-chosen prose may wrap the allowed value, including a second promise
        # before/after it. Only this closed server-written question can use customer data.
        if context.surface != "dm" or proposal.template.strip() or proposal.fact_sources:
            return GroundedReply(errors=("CUSTOMER_ATTRIBUTION_INVALID",))
        message = db.scalar(
            select(Message)
            .where(
                Message.id == source.message_id,
                Message.workspace_id == context.workspace.workspace_id,
                Message.social_account_id == context.account_id,
                Message.conversation_id == thread.dm_conversation_id,
                Message.direction == "inbound",
                Message.sender_kind == "customer",
                Message.is_deleted.is_(False),
            )
            .limit(1)
        )
        text = message.text if message is not None else None
        if not text or source.start >= source.end or source.end > len(text):
            return GroundedReply(errors=("CUSTOMER_SOURCE_INVALID",))
        value = text[source.start : source.end]
        pattern = _DATE if source.kind == "date" else _TIME
        if pattern.fullmatch(value) is None:
            return GroundedReply(errors=("CUSTOMER_VALUE_INVALID",))
        label = "tarih" if source.kind == "date" else "saat"
        question = (
            f"“{value}” belirttiniz. Tercih ettiğiniz {label} bu mu?"
            if proposal.language == "tr"
            else f"You mentioned “{value}”. Is that your preferred {source.kind}?"
        )
        return GroundedReply(question, customer_source=source.message_id)
    keys = placeholder_keys(proposal.template)
    if len(keys) > 20:
        return GroundedReply(errors=("SOURCE_LIMIT",))
    evidence = {source.id: source.version for source in proposal.fact_sources}
    if len(evidence) != len(proposal.fact_sources):
        return GroundedReply(errors=("SOURCE_DUPLICATE",))
    rows = (
        list(
            db.scalars(
                select(BusinessFact)
                .where(
                    visible_predicate(db, clock, context.workspace),
                    BusinessFact.key.in_(keys),
                )
                .limit(20)
            )
        )
        if keys
        else []
    )
    if set(keys) != {row.key for row in rows} or evidence != {
        row.id: row.current_version for row in rows
    }:
        return GroundedReply(errors=("SOURCE_STALE_OR_FORGED",))
    rendered: RenderResult = render(
        proposal.template,
        [as_usable(row, context.workspace, proposal.language) for row in rows],
        proposal.language,
    )
    if not rendered.ok:
        return GroundedReply(errors=("RENDER_INVALID",))
    claims = validate_claims(rendered.text, rendered, proposal.language)
    if not claims.passed:
        return GroundedReply(errors=tuple(sorted({issue.code for issue in claims.issues})))
    if length_issue(rendered.text, max_bytes=1000) or not rendered.text.strip():
        return GroundedReply(errors=("REPLY_LENGTH_INVALID",))
    return GroundedReply(rendered.text, rendered.used)
