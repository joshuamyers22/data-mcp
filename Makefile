.PHONY: setup format lint typecheck test check audit build export-check
.PHONY: integration-up integration-test integration-down

INTEGRATION_COMPOSE = docker compose -f compose.integration.yml -p data-mcp-integration
DATA_MCP_TEST_POSTGRES_PORT ?= 55432
DATA_MCP_TEST_MYSQL_PORT ?= 43306
DATA_MCP_TEST_MONGODB_PORT ?= 47017
DATA_MCP_TEST_S3_PORT ?= 45000
export DATA_MCP_TEST_POSTGRES_PORT
export DATA_MCP_TEST_MYSQL_PORT
export DATA_MCP_TEST_MONGODB_PORT
export DATA_MCP_TEST_S3_PORT

setup:
	uv sync --frozen --all-extras --dev
format:
	uv run ruff format .
lint:
	uv run ruff check .
	uv run ruff format --check .
typecheck:
	uv run pyright
test:
	uv run --frozen pytest -q
check: lint typecheck test
audit:
	uv audit --preview-features audit-command --locked --no-dev
build:
	uv build
export-check:
	uv export --frozen --all-extras --no-dev --no-emit-project --output-file requirements.runtime.txt
	git diff --exit-code -- requirements.runtime.txt
integration-up:
	$(INTEGRATION_COMPOSE) up -d --wait
integration-test:
	DATA_MCP_TEST_DSN=postgresql://postgres:data_mcp_test_only@127.0.0.1:$(DATA_MCP_TEST_POSTGRES_PORT)/data_mcp_test \
	DATA_MCP_MYSQL_TEST_DSN=mysql://root:data_mcp_test_only@127.0.0.1:$(DATA_MCP_TEST_MYSQL_PORT)/data_mcp_test \
	DATA_MCP_MONGODB_TEST_URI=mongodb://127.0.0.1:$(DATA_MCP_TEST_MONGODB_PORT) \
	DATA_MCP_S3_TEST_ENDPOINT=http://127.0.0.1:$(DATA_MCP_TEST_S3_PORT) \
	AWS_ACCESS_KEY_ID=testing AWS_SECRET_ACCESS_KEY=testing \
	AWS_DEFAULT_REGION=us-east-1 AWS_EC2_METADATA_DISABLED=true \
	uv run --frozen pytest -q
integration-down:
	$(INTEGRATION_COMPOSE) down --volumes
