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
hash-pinned deployment export with every connector extra. `make export-check`
verifies parity in Git checkouts.

`make setup` installs every connector extra so the checked environment matches the
container export. `make check` runs Ruff, strict Pyright, pytest backend/failure
tests, and an actual stdio MCP roundtrip. Network integration tests are opt-in when
their service environment variables are absent. Run `make integration-up`,
`make integration-test`, and `make integration-down` to exercise disposable
PostgreSQL, MySQL, MongoDB, and S3-compatible services using the pinned images in
`compose.integration.yml`. Tests create and remove unique schemas, tables,
collections, and buckets. Never point integration-test variables at production.

CI provisions the same four service types and runs the opt-in tests as part of the
normal gate. This validates driver and protocol behavior, not public-cloud IAM,
provider TLS chains, latency, quotas, or billing.

Run `make build` before `docker build -t data-mcp:local .`; the image installs the
export with hash verification and the locally built wheel without re-resolving.
The Dockerfile is supplied but target-host image validation and immutable base-image
pinning remain release checks. No container or package has been published.
