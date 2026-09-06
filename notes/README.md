# Work Notes

Use a tracked work note only when a task spans sessions, needs a handoff, records
an incident/experiment, or has coordination value beyond Git and the issue
tracker. Create it as `notes/YYYY-MM-DD-short-topic.md` from
`templates/WORK_NOTE.md`.

Keep disposable thinking, command output, and local task scratch in `.work/`,
which is ignored. Do not commit raw telemetry exports, stack dumps, prompts,
credentials, personal or client data, or hidden reasoning. A tracked note records
observations, concise conclusions, reproduction evidence, and decisions—not a
transcript.

Close every tracked note by promoting durable knowledge to the appropriate source
of truth (`PROJECT_MEMORY.md`, an ADR, documentation, tests, or an issue), then
marking the note closed or deleting it when it no longer has audit value.
