# Mos Eisley integration

The `feat/data-mcp-client` branch in
[Mos Eisley](https://github.com/joshuamyers22/mos-eisley/tree/feat/data-mcp-client)
adds explicit local MCP discovery/calls and an adapter for its canonical agent loop.
It was developed from Mos Eisley main `950cb88`, against data-mcp `2019983`.

The stacked `feat/remote-mcp-http` branch adds connections to user-selected hosted
servers using Streamable HTTP and bearer tokens. See its
[remote configuration and limits](https://github.com/joshuamyers22/mos-eisley/blob/feat/remote-mcp-http/docs/MCP_DATA.md#connect-your-own-hosted-server).
The further `feat/mcp-oauth` branch implements OAuth for pre-registered public
clients, with OS keychain credentials, refresh and logout. See the
[OAuth guide](https://github.com/joshuamyers22/mos-eisley/blob/feat/mcp-oauth/docs/MCP_DATA.md#oauth-login-and-logout).
This data-mcp server continues to run over stdio.

Install the local-client branch (or its HTTP extension) and follow the
[client guide](https://github.com/joshuamyers22/mos-eisley/blob/feat/data-mcp-client/docs/MCP_DATA.md).
The read/write example uses this repository's ignored `config.toml`; the Ana Lite
example uses a locally prepared `config.ana.toml` copied from
`config.ana.example.toml`. Set actual root paths, reviewed ontology and credential
environment references. Keep `config.ana.toml` and client configs private.

From the Mos Eisley checkout, after adapting its example paths and environment:

```sh
uv run --frozen mos mcp-list --config /absolute/path/mcp-data-rw.json
uv run --frozen mos mcp-call --config /absolute/path/mcp-data-rw.json \
  --call examples/mcp-list-sources.json
```

The client requires all named environment variables to be present and all selected
tools to exist. Remove unused source definitions and environment references for a
Parquet-only setup. Read/write grants are explicit per tool. Ana Lite's client
profile excludes writes, and the server independently enforces `access_mode="analysis"`.

The default client result limit is 4,000 bytes, including the canonical JSON result
and escaped textual/structured representations. This is smaller than data-mcp's
default 256 KiB. Use aggregate queries or narrower selections; align any larger
client limit with the agent's resolved output reserve. Oversized results fail and
are never silently shortened. A write may already be committed when its response
is rejected, lost or timed out; inspect the source before retrying.

## Verification record — 2026-09-09

Objective: demonstrate the full Mos Eisley → stdio data-mcp → source path, while
retaining explicit grants, immutable promoted definitions and uncertain-write
handling. The passing threshold is real fixture roundtrips on both backends and
the Mos Eisley client gate. No paid provider calls or production source access are
needed. Stop after these checks; live HDD/cloud TLS validation needs deployment
inputs. This record covers a material integration and is not independent review.

Executed Mos Eisley tests:

- Parquet create, append, SELECT, replace; promoted Ana Lite context/metric listing
  and revision-bound count; write rejection in the analysis client profile.
- Disposable PostgreSQL 17: INSERT and UPDATE committed through MCP, SELECT in a
  fresh MCP server session, then DELETE and empty-result verification. The test
  created and removed its own unique schema; the container was disposable.
- Client fixture checks include a two-turn canonical agent, explicit environment
  filtering, schema lowering and rejection, missing/duplicate tools, deadlines,
  cancellation, process cleanup, oversized results and redacted wire diagnostics.

The cross-repository tests live in Mos Eisley's
[`tests/test_mcp_data_integration.py`](https://github.com/joshuamyers22/mos-eisley/blob/feat/data-mcp-client/tests/test_mcp_data_integration.py).
They take `DATA_MCP_TEST_PYTHON` and an optional **disposable** `DATA_MCP_TEST_DSN`.
Ordinary CI uses self-contained stdio fixtures; cross-repository tests are opt-in.
Full client gate details are retained in its
[verification record](https://github.com/joshuamyers22/mos-eisley/blob/feat/data-mcp-client/docs/MCP_DATA_VERIFICATION.md).

The paid `openai-run` and critic/judge paths still expose no MCP tools. The adapter
is ready for a separately bounded analytical conversation; it does not supply
multi-turn spend admission, provider transfer consent, retained source snapshots,
golden evaluation results, automatic learning or an Ana Lite UI. Actual mounted
HDD paths, role grants and cloud certificate verification remain deployment inputs.
