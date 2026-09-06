.PHONY: setup format lint typecheck test check audit build export-check
setup:
	uv sync --frozen --dev
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
	uv export --frozen --no-dev --no-emit-project --output-file requirements.runtime.txt
	git diff --exit-code -- requirements.runtime.txt
