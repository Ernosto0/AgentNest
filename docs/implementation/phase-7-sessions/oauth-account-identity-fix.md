# OAuth account identity follow-up

**Date:** 2026-10-25 (Europe/Istanbul).
**Status:** local fix applied, synthetic regressions passed, and the owner's fresh
OAuth connection independently verified. Gate 2 and the remaining real-account
criteria stay open. The owner-authorized `messages` subscription is enabled;
end-to-end delivery and native-reply detection remain pending.

## Observed failure

The owner completed Instagram consent, but a first connection returned
`ACCOUNT_MISMATCH`, whose UI text asks the owner to reconnect an already-linked
account. A read-only development database check found no Meta social-account row;
the consumed OAuth state was for `connect`, without an existing account reference.
The adapter log recorded a successful profile read. In this path, the mismatch
check compares the token exchange's `user_id` with the Graph profile's `user_id`.
It incorrectly assumes those values are always interchangeable. No raw provider
payload, token, authorization code or real account ID is recorded in this report.

## Change

After the long-lived token exchange, the OAuth client resolves the authenticated
owner through versioned Graph `/me?fields=user_id`, using a Bearer header. It
returns that profile identifier for subsequent account comparisons and storage.
Malformed or unauthorized owner responses fail closed; the client does not fall
back to the exchange identifier. The independent profile check and same-account
reconnect guard remain enforced. State/session/role checks, encryption, actual
granted-scope capability detection and transaction boundaries are unchanged.

The API was restarted locally with this change and access logging disabled.
Database readiness and the public provider-policy endpoint returned HTTP 200,
with Meta enabled. The existing worker, frontend and owner-run tunnel were kept.
No code was pushed, and no development data was reset.

## Verification

- 186 tests passed across OAuth client, Meta adapter and OAuth integration tests.
- Synthetic exchange/profile identifiers deliberately differ; successful first
  connection stores the token owner's profile identifier and encrypts its token.
- A profile different from the resolved owner is still rejected; reconnecting a
  different account remains rejected. Invalid identity responses and denied
  owner lookup do not connect an account. Sensitive values remain absent from logs.
- Ruff lint/format and targeted mypy passed; all 19 import contracts passed.
- Tests used a uniquely owned `agentnest_oauth_identity_*_test` database with
  fake/mock/local settings, explicit blank live-test inputs and synthetic HTTP
  transports. No test made a real Instagram request.
- Ignored local evidence: `backend/var/instagram-setup/oauth-identity-tests.log`,
  `oauth-identity-tests.xml`, and `oauth-identity-test-database.json`.

The owner completed a fresh UI connection after the fix. Read-only verification
found one real connected account, an encrypted/decryptable token with approximately
60 days remaining, all three requested scopes, and a real connection audit entry.
Live profile lookup matched the stored account identifier and owner-reported
username. Publishing-quota lookup succeeded (0 used, limit 100 per 24 hours).
Frontend/API returned HTTP 200, the public webhook echoed its verification challenge,
and the API/worker/frontend/owner-run tunnel were running. There were no failed or
uncertain operations for the connected real account. No message or post was sent.
The connected workspace has no automatic action policies; missing policies default
to approval. Reply drafts therefore require owner approval under the current policy.

The account's `GET /subscribed_apps` returned HTTP 200 with an empty subscription
list. Consequently, successful OAuth and callback verification alone did not establish
incoming messaging delivery. No real inbound event had been recorded at that check.
The owner then explicitly authorized activation. An initial read failed before mutation
with a connection error. Meta subsequently rejected `message_echoes` with error 100:
it is not an allowed `subscribed_fields` value for this app/API. The failed requests
left subscriptions empty. The valid requested subset, `messages`, was then activated
successfully (HTTP 200, `success=true`), and a fresh subscription read confirmed it.
No unsupported substitute field was enabled. Native-reply delivery is not inferred
from this configuration and still needs a live test; no test DM or post was sent.
Reply policies remain at the approval default. Sanitized evidence is saved in
`connected-account-check.json`, `connected-routing-check.json`, and
`webhook-subscription-activation.json` under the ignored local evidence directory;
earlier failed attempts are retained there separately.

Meta's business-login/get-started/webhook documentation returned HTTP 429 during
this investigation; no broader platform research criterion is claimed complete.

The separate **Offline demo AI** label reflects `LLM_PROVIDER=fake`. It does not
select the Instagram provider, and that AI configuration was not changed here.
