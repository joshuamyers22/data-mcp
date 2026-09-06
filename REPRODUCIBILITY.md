# Reproducibility

A clean checkout must reproduce installation, checks, tests, and build artifacts
using the committed runtime version and `uv.lock`:

```sh
make setup
make check
make audit
make build
```

Record external inputs, configuration, tool/runtime versions, and commands needed
to reproduce material results. Never depend silently on developer-machine state.

Template provenance: production-project-template python-cli archetype at
`3d467040ba760efe9795f67f07d5a2ccf364282b`, generated using `tools/create_project.py`.
The resolver-generated `uv.lock` is authoritative; `requirements.runtime.txt` is its
hash-pinned deployment export. `make export-check` verifies parity in Git checkouts.

`make check` runs Ruff, strict Pyright, pytest backend/failure tests, and an actual
stdio MCP roundtrip. Set `DATA_MCP_TEST_DSN` to a disposable PostgreSQL database to
include database integration tests; CI provides PostgreSQL 17. Tests create/drop
unique schemas. Never use a production database for this variable.

Run `make build` before `docker build -t data-mcp:local .`; the image installs the
export with hash verification and the locally built wheel without re-resolving.
The Dockerfile is supplied but target-host image validation and immutable base-image
pinning remain release checks. No container or package has been published.
