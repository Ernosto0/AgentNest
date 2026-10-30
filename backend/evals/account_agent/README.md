# Account-agent scripted journeys

`initial_journeys.yaml` is a fixed, versioned set of 60 two-turn journeys in
Turkish and English across beauty/wellness, retail and fitness. The integration
test drives each case through the durable wake/step/job path with a scripted
fake model, a mock account and verified facts. It checks broker validation,
observation and completion after a worker restart. It does **not** score whether
a model selected the right tool or wrote an appropriate answer to each prompt.

The real-model quality gate requires a separately authorized spend budget and
human review. Do not count this scripted set as that gate.

Run `uv run python -m evals.account_agent` from `backend/`. This command also
executes focused owner question/resume, exact human approval, public context
isolation, moderation/reconciliation, private-reply linkage and owner content
clarification journeys. CI runs it as a separate
offline gate after the legacy fake evals.
