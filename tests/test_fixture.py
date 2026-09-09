import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from data_mcp.config import Settings
from data_mcp.data import DataStore
from data_mcp.fixture import CASES, check_pack, create_pack, verify_pack
from data_mcp.sql import DataError


def pack_at(tmp_path: Path) -> tuple[Path, str]:
    result = create_pack(tmp_path.resolve())
    return Path(result["pack"]), result["manifest_sha256"]


def test_real_mcp_answers_and_golden_separation(tmp_path: Path) -> None:
    pack, pin = pack_at(tmp_path)
    report = asyncio.run(verify_pack(pack, pin))
    assert report["checked_answers"] == 12
    assert report["file_hashes_match_before_and_after"] is True
    assert report["model_quality_measured"] is False
    raw = Settings.load(pack / "raw.toml")
    promoted = Settings.load(pack / "promoted.toml")
    assert raw.ontology_file is None
    assert raw.parquet == promoted.parquet
    assert list((pack / "data").iterdir()) == [pack / "data" / "lines.parquet"]
    store = DataStore(raw)
    with pytest.raises(DataError):
        store.query_parquet("fixture", ["../golden/cases.json"], "SELECT * FROM data")
    with pytest.raises(DataError):
        store.write_parquet("fixture", "lines.parquet", '[{"value":1}]', "replace")
    second, _ = pack_at(tmp_path)
    assert second != pack
    check_pack(pack, pin)


@pytest.mark.parametrize(
    "index,old,new",
    [
        (0, "status = 'completed'", "status IN ('completed', 'cancelled')"),
        (0, "< DATE '2026-02-01'", "<= DATE '2026-02-01'"),
        (0, ">= DATE '2026-01-01'", "> DATE '2026-01-01'"),
        (1, "COALESCE(discount_cents, 0)", "discount_cents"),
        (2, "COUNT(DISTINCT order_id)", "COUNT(*)"),
        (3, "SUM(quantity)", "SUM(ABS(quantity))"),
        (
            5,
            "COALESCE(SUM(quantity * unit_price_cents - "
            "COALESCE(discount_cents, 0)), 0)",
            "SUM(quantity * unit_price_cents - COALESCE(discount_cents, 0))",
        ),
    ],
)
def test_cases_detect_wrong_sql(tmp_path: Path, index: int, old: str, new: str) -> None:
    pack, _ = pack_at(tmp_path)
    case = CASES[index]
    store = DataStore(Settings.load(pack / "raw.toml"))
    sql = case.sql.replace(old, new)
    assert sql != case.sql
    assert store.query_parquet("fixture", ["lines.parquet"], sql)["rows"] != [
        [case.expected]
    ]


@pytest.mark.parametrize(
    "mutation",
    ["pin", "data", "labels", "config", "extra", "symlink", "hardlink", "public"],
)
def test_invalid_packs_fail_before_execution(tmp_path: Path, mutation: str) -> None:
    pack, pin = pack_at(tmp_path)
    target = pack / "data" / "lines.parquet"
    if mutation == "pin":
        pin = "0" * 64
    elif mutation in {"data", "labels", "config"}:
        target = {
            "data": target,
            "labels": pack / "golden/cases.json",
            "config": pack / "raw.toml",
        }[mutation]
        target.write_bytes(target.read_bytes() + b" ")
    elif mutation == "extra":
        (pack / "data" / "extra.parquet").write_bytes(b"extra")
    elif mutation == "symlink":
        moved = tmp_path / "moved.parquet"
        target.rename(moved)
        target.symlink_to(moved)
    elif mutation == "hardlink":
        os.link(target, tmp_path / "linked.parquet")
    else:
        target.chmod(0o644)
    with pytest.raises(ValueError):
        check_pack(pack, pin)


def test_private_parent_and_cli_failure(tmp_path: Path) -> None:
    tmp_path.chmod(0o755)
    with pytest.raises(ValueError):
        create_pack(tmp_path.resolve())
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "data_mcp.fixture",
            "create",
            "--output-root",
            str(tmp_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not result.stdout
    assert str(tmp_path) not in result.stderr
    tmp_path.chmod(0o700)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "data_mcp.fixture",
            "create",
            "--output-root",
            str(tmp_path.resolve()),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    receipt = json.loads(result.stdout)
    check_pack(Path(receipt["pack"]), receipt["manifest_sha256"])
