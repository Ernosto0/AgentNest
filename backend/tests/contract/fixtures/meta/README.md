# Synthetic offline Meta contracts

Every JSON in this directory was authored for offline Phase 7 Session 2 tests on
2026-10-23. **None is a recorded response or evidence of live platform behavior.**
`_fixture_source` explicitly labels that provenance without changing the modeled fields.
IDs, tokens, trace IDs and media URLs are synthetic. No production credentials are used.

The response shapes implement the repository's Session 2 brief and provisional I3-I5
contracts. The official Meta content-publishing, quota-reference and messaging pages
could not be retrieved during this session (access failure/HTTP 429); third-party
search results were not used as authority. Gate 2/V-05 and P7-00's final research
re-plan remain pending. Real sanitized recordings must be added and reviewed before
live acceptance; these fixtures must never be relabeled as recordings.

Container PUBLISHED intentionally has no media ID: the current documented contract
allows `ContainerStatus.media_id=None`. The executor can record a verified publication
without inventing a permalink. Quota duration is interpreted as seconds; quota total
is read from the response, never hardcoded by the adapter.
