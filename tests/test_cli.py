import subprocess
import sys
from pathlib import Path


def test_check_needs_no_database(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('[postgres.test]\ndsn_env="UNSET_DATA_MCP_TEST_DSN"\n')
    result = subprocess.run(
        [sys.executable, "-m", "data_mcp.cli", "--config", str(config), "--check"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert '"credential_configured": false' in result.stdout


def test_invalid_config_hides_raw_values(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text('secret="not-for-output"')
    result = subprocess.run(
        [sys.executable, "-m", "data_mcp.cli", "--config", str(config), "--check"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "not-for-output" not in result.stderr
