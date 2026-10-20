"""Inputs and outputs of the AI tasks (agent-runtime.md §3, §6).

Output models double as the *provider* schema (OpenAI structured outputs, strict mode), so they
follow its rules: an object at the root, closed objects, every field present, ``Literal`` tags
for unions, and no length/pattern keywords (those are checked by the task's post-validator).
The model's output is only ever a *proposal*: it is validated here, then resolved and checked
by deterministic code before anything happens (ADR-007, INV-04).
"""

from typing import Any, Literal

from pydantic import BaseModel, model_validator

# --- interpret_command: input ---------------------------------------------------------------


class FactCatalogEntry(BaseModel):
    """One of the owner's own facts, as the interpreter sees it."""

    key: str
    label: str
    category: str
    value_type: str
    status: str  # verified | unverified
    current_value_display: str


class RegistryEntry(BaseModel):
    """A command type the interpreter may choose (static text, same for every workspace)."""

    type: str
    description: str
    parameters: dict[str, str]  # parameter name -> short description


class InterpretCommandInput(BaseModel):
    text: str
    user_locale: str
    workspace_locale: str
    timezone: str
    now_local: str  # ISO 8601 in the workspace timezone (INV-19)
    currency: str
    fact_catalog: list[FactCatalogEntry]
    registry: list[RegistryEntry]
    # content_catalog (upcoming content, as short aliases) arrives with Phase 5.


MAX_COMMAND_CHARS = 1000
MAX_CATALOG_FACTS = 300

# --- interpret_command: output --------------------------------------------------------------


class NormalizedMoney(BaseModel):
    kind: Literal["money"]
    amount: str  # decimal string, e.g. "7000.00"
    currency: str  # ISO 4217


class NormalizedText(BaseModel):
    kind: Literal["text"]
    text: str


class NormalizedBoolean(BaseModel):
    kind: Literal["boolean"]
    value: bool


# Plain unions (``anyOf``), not ``Field(discriminator=...)``: that emits ``oneOf``, which the
# provider's strict mode does not accept. The ``Literal`` tags keep validation unambiguous.
NormalizedValue = NormalizedMoney | NormalizedText | NormalizedBoolean


class QueryActivitySummary(BaseModel):
    type: Literal["query.activity_summary"]
    period: Literal["today", "yesterday", "last_7_days"]


class QueryPendingApprovals(BaseModel):
    type: Literal["query.pending_approvals"]


class QueryFact(BaseModel):
    type: Literal["query.fact"]
    fact_key: str


class UpdateFact(BaseModel):
    type: Literal["knowledge.update_fact"]
    fact_key: str
    raw_value_text: str  # the value exactly as the owner typed it
    normalized_value: NormalizedValue | None  # the model's reading; code re-parses and compares
    reason: str | None


class UpdateBrandVoice(BaseModel):
    type: Literal["knowledge.update_brand_voice"]
    instruction: str
    proposed_guidelines: str  # the full new text


class Clarify(BaseModel):
    """The command is ambiguous. The question shown to the owner is built by code from the
    candidates; the model's wording is never displayed."""

    type: Literal["clarify"]
    intent: Literal["knowledge.update_fact", "query.fact", "knowledge.update_brand_voice"]
    candidate_fact_keys: list[str]
    raw_value_text: str | None


UnsupportedReason = Literal[
    "publish", "send_message", "approve", "manage_account", "settings", "members", "other"
]


class Unsupported(BaseModel):
    """Not in the registry by design: approve, publish now, send a message, connect accounts,
    change automation policies, manage members (agent-runtime.md §3). The suggestions shown to
    the owner are chosen by code from ``reason``."""

    type: Literal["unsupported"]
    reason: UnsupportedReason


CommandInterpretation = (
    QueryActivitySummary
    | QueryPendingApprovals
    | QueryFact
    | UpdateFact
    | UpdateBrandVoice
    | Clarify
    | Unsupported
)

INTERPRETATION_TYPES = frozenset(
    {
        "query.activity_summary",
        "query.pending_approvals",
        "query.fact",
        "knowledge.update_fact",
        "knowledge.update_brand_voice",
        "clarify",
        "unsupported",
    }
)


class InterpretCommandOutput(BaseModel):
    """Provider schema: structured outputs need an object at the root, so the union sits
    inside this wrapper."""

    interpretation: CommandInterpretation

    @model_validator(mode="before")
    @classmethod
    def _unknown_type_is_unsupported(cls, data: Any) -> Any:
        """A ``type`` outside the registry (``approve``, ``publish_now``, anything invented)
        is never executable: it becomes ``unsupported`` here, deterministically (INV-04)."""
        if isinstance(data, dict):
            inner = data.get("interpretation")
            if isinstance(inner, dict) and inner.get("type") not in INTERPRETATION_TYPES:
                return {"interpretation": {"type": "unsupported", "reason": "other"}}
        return data


# --- extract_fact_candidates ----------------------------------------------------------------


class CatalogKey(BaseModel):
    key: str
    label: str
    value_type: str
    description: str


class ExtractFactsInput(BaseModel):
    text: str  # untrusted pasted text
    catalog: list[CatalogKey]
    workspace_locale: str
    currency: str


MAX_EXTRACT_CHARS = 8000
MAX_EXTRACT_ITEMS = 50


class ExtractedItem(BaseModel):
    fact_key: str
    raw_value_text: str
    normalized_value: NormalizedValue | None
    source_excerpt: str


class ExtractFactsOutput(BaseModel):
    items: list[ExtractedItem]


# --- draft_reply (agent-runtime.md §4) --------------------------------------------------------

Intent = Literal[
    "greeting",
    "pricing",
    "hours",
    "location_contact",
    "services",
    "booking",
    "promotions",
    "faq",
    "complaint",
    "refund_request",
    "discount_request",
    "sensitive",
    "other",
]
ReplyFlag = Literal[
    "complaint",
    "refund",
    "discount",
    "legal",
    "health_safety",
    "abusive",
    "personal_data",
    "injection_suspected",
]
MAX_TEMPLATE_BYTES = 900  # before rendering; the rendered reply must fit 1000 bytes in total
MAX_HISTORY_MESSAGES = 10
MAX_HISTORY_CHARS = 1000


class DraftFact(BaseModel):
    """A usable fact the reply may quote, only through its placeholder."""

    key: str
    label: str
    value_type: str
    value_display: str
    placeholder: str


class DraftApprovedAnswer(BaseModel):
    id: str
    intent: str
    example_questions: list[str]
    answer_template: str
    status: str  # active | needs_review


class DraftMessage(BaseModel):
    role: Literal["customer", "business"]
    text: str  # untrusted: the customer's own words


class DraftReplyInput(BaseModel):
    reply_language: str  # detected by code; the model may not switch
    facts: list[DraftFact]
    price_disclosure: Literal["share", "do_not_share"]
    approved_answers: list[DraftApprovedAnswer]
    brand_voice: str | None
    conversation: list[DraftMessage]  # the last messages, oldest first
    # Set on the one regeneration: what was wrong with the previous proposal.
    validator_feedback: list[str]


class ReplyProposal(BaseModel):
    intent: Intent
    flags: list[ReplyFlag]
    can_answer: bool
    needs_human: bool
    approved_answer_id: str | None
    reply_template: str | None
    used_fact_keys: list[str]
    language: str


# --- draft_content (agent-runtime.md §5) ------------------------------------------------------

ContentKind = Literal["feed_image", "story_image"]
MAX_HASHTAGS = 10
MAX_CAPTION_TEMPLATE_CHARS = 2200  # Instagram's caption limit, before rendering
MAX_OVERLAY_SUGGESTIONS = 5
MAX_OVERLAY_TEMPLATE_CHARS = 200  # a guard; the 3 x 40 rule is checked on the rendered text
MAX_TITLE_CHARS = 80
MAX_VISUAL_NOTES_CHARS = 1000
MAX_OBJECTIVE_CHARS = 1000
MAX_NOTES_CHARS = 2000


class DraftContentInput(BaseModel):
    content_type: ContentKind
    objective: str  # the owner's own words: trusted, but still data
    notes: str | None
    language: str  # the workspace default locale; the model may not switch
    facts: list[DraftFact]  # usable facts only, each quotable through its placeholder only
    brand_voice: str | None


class CommercialClaim(BaseModel):
    """A claim the model makes that a customer could hold the business to ("free trial").

    ``fact_key`` names the fact that backs it; ``null`` means the model has no fact for it. Code
    decides whether that fact was really rendered: a claim without one is an issue."""

    claim: str
    fact_key: str | None


class ContentProposal(BaseModel):
    title: str  # internal label
    caption_template: str | None  # feed_image only; critical values only as placeholders
    overlay_text_suggestions: list[str]  # story_image only; placeholders allowed
    visual_notes: str  # concept for the owner or photographer
    hashtags: list[str]  # at most 10; code appends them to the caption
    used_fact_keys: list[str]
    commercial_claims: list[CommercialClaim]
