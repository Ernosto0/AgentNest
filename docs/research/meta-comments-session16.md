# Session 16 Meta comment contract evidence

Checked **2026-10-29**, Europe/Istanbul. Status: **externally pending**.
No authenticated request, webhook capture, account mutation or paid evaluation occurred.
This refresh does not reconfirm the older 2026-10-15 documentation claims.

| Primary source attempted | Actual retrieval result | Open research |
|---|---|---|
| [Comment moderation](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/comment-moderation) | Browser retrieval reported inaccessible; no primary text | R75-01/02/03/06: scope/access, owner/media fields, events, pagination, native moderation, acknowledgement/readback/errors |
| [Messaging API](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/messaging-api) | HTTP 429 Too Many Requests | R75-04/05/06: private eligibility/count/expiry, recipient identity, conversation opening, quotas/errors |
| [Instagram webhooks](https://developers.facebook.com/docs/instagram-platform/webhooks) | HTTP 429 Too Many Requests | R75-01/02/05/06: subscription/access, authentic comment changes, cross-surface identity |
| [Old private replies path](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-instagram-login/private-replies) | Browser retrieval reported inaccessible; no primary text | R75-04/05: current endpoint, rule/identity/readback contracts |

Search attempts failed at transport level. No search snippet or third-party example
was promoted to primary evidence. No document title/version beyond these URL labels
could be read. All six R75 items remain open.

## Offline scaffold

`SyntheticMetaCommentProvider` requires an exact `httpx.MockTransport`; the runtime
registry never constructs it. It exercises fixed-host Bearer transport, bounded
cursor pagination, content-free errors and no automatic retries. Fixture assumptions:

- `GET /{media}` with `id,owner`, `GET /{media}/comments` and `GET /{comment}`
  with `id,media,timestamp,text,hidden`; sources must resolve to owned media.
- `POST /{comment}/replies` with `message`, returning an ID.
- `POST /{comment}` with Boolean `hide`, or `DELETE /{comment}`, acknowledging
  `success:true`. This does not fabricate independent state readback.
- `POST /{account}/messages` with `recipient.comment_id` and `message.text`, returning
  `message_id` and optional explicit `recipient_id`. No identity is guessed.
- The mock's conservative seven-day private deadline, solely provisional. Future
  source timestamps and elapsed deadlines reject.

Paths, fields, scopes, eligibility and response shapes remain **unverified assumptions**.
The production adapter rejects comment reads/effects/lookups. Its webhook codec ignores
synthetic comments. OAuth reports `comment_read`, `comment_reply`, `comment_moderate`,
`comment_private_reply` false, including with `instagram_business_manage_comments`.
Consent and subscription expansion remain gated. Existing canonical `/me` identity,
encryption, reconnect and disconnect fences are preserved.

Local operation keys have no assumed remote idempotency/readback meaning. Lookups
return no evidence: missing replies, current hidden state and 404 cannot prove this
operation succeeded. Lost, malformed, gateway and generic transient mutation responses
are unknown. Definitive rate/auth/permission rejections retain typed handling. The
application ledger owns deduplication and reconciliation.

## Remaining founder checks

Obtain readable official contracts and authentic sanitized requests/responses/webhooks
for each capability, with date, API version, actual grants, access level and account
type. Replace assumptions and review capability mapping before real enablement.
Verify grant loss/reconnect, ownership, pagination, native changes, deadlines, quotas,
errors and uncertainty. Private reply separately needs evidenced eligibility, one-shot
reservation, recipient identity and DM continuation; a matching username is insufficient.

The harness requires exact media/comment targets and one selected effect per run:
`read`, `reply`, `private_reply`, `hide`, `unhide`, `delete`. New cases remain gated
off; credentials/targets cannot override the evidence gate. No arbitrary comment
selection or mutation retry occurs. After reviewed evidence enables the gate, use
founder-owned disposable targets and separately authorized live actions. Direct probes
do not prove the application operation path; Session 18 must retain end-to-end evidence.
G7.5-D and AC75-23 are not passed.
