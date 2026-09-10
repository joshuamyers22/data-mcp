# Contributing

Issues and pull requests are welcome. For a substantial feature or new connector,
open an issue first so the interface, dependency cost, and security boundary can be
agreed before implementation.

## Development setup

```sh
git clone https://github.com/joshuamyers22/data-mcp.git
cd data-mcp
uv sync --frozen --all-extras --dev
make check
make build
```

To run the complete integration suite against disposable PostgreSQL, MySQL,
MongoDB, and S3-compatible services:

```sh
make integration-up
make integration-test
make integration-down
```

Docker Compose uses nonstandard localhost ports by default. Override
`DATA_MCP_TEST_POSTGRES_PORT`, `DATA_MCP_TEST_MYSQL_PORT`,
`DATA_MCP_TEST_MONGODB_PORT`, or `DATA_MCP_TEST_S3_PORT` before both `up` and
`test` if needed. `integration-down` removes the stack and its disposable volumes.

Keep changes bounded and include tests for changed behavior and failure paths. New
connectors must keep secrets out of configuration examples, arguments, results, and
logs; enforce global result limits and `access_mode="analysis"`; document backend
authority and retry semantics; and avoid importing optional dependencies until that
connector is used.

Pull requests should describe the outcome, compatibility impact, risks, verification
evidence, and rollback or forward-fix path. Do not use production credentials or data
in tests. By contributing, you agree that your contribution is licensed under the
project's MIT License.

Please follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) in project spaces. Report
security problems through the private process in [SECURITY.md](SECURITY.md), not a
public issue.
