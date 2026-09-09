"""Private synthetic development cases, checked through real stdio MCP sessions."""

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import pyarrow as pa
import pyarrow.parquet as _pq
from mcp import Client
from mcp.client.stdio import StdioServerParameters

pq: Any = _pq

Mode = Literal["raw", "promoted"]
MODES: tuple[Mode, ...] = ("raw", "promoted")
MAX_BYTES = 65536
JANUARY = (
    "status = 'completed' AND CAST(ordered_on AS DATE) >= DATE '2026-01-01' "
    "AND CAST(ordered_on AS DATE) < DATE '2026-02-01'"
)
CONVENTIONS = (
    "Synthetic development cases, not independently reviewed domain definitions. "
    "Each row is one order line; order IDs repeat across lines. Include completed "
    "lines only. Dates are calendar dates with half-open month boundaries. "
    "Quantity and discounts are signed for returns. Null discount means zero "
    "for net amounts, while missing-discount counts retain that distinction. "
    "Net cents = quantity * unit_price_cents - COALESCE(discount_cents, 0). "
    "Empty net totals are zero. Integer cents are synthetic units."
)
# Hand-worked January totals: gross 2000+500+2100-1000+1200 = 4800;
# net 1900+500+1900-900+1200 = 4600; units 2+1+3-1+1 = 6.
# A has two lines; distinct completed orders are A, B, R, D. A2 and D lack discounts.
ROWS = (
    ("Z", "2025-12-31", "completed", 1, 9999, None),
    ("A", "2026-01-01", "completed", 2, 1000, 100),
    ("A", "2026-01-10", "completed", 1, 500, None),
    ("B", "2026-01-15", "completed", 3, 700, 200),
    ("C", "2026-01-20", "cancelled", 10, 10000, 0),
    ("R", "2026-01-25", "completed", -1, 1000, -100),
    ("D", "2026-01-31", "completed", 1, 1200, None),
    ("E", "2026-02-01", "completed", 4, 800, 0),
)
COLUMNS = (
    "order_id",
    "ordered_on",
    "status",
    "quantity",
    "unit_price_cents",
    "discount_cents",
)


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    sql: str
    units: str
    expected: int
    family: str = "synthetic_order_lines"
    split: str = "development"


CASES = (
    Case(
        "january_gross",
        "What are completed January 2026 gross signed cents?",
        f"SELECT SUM(quantity * unit_price_cents) AS total FROM data WHERE {JANUARY}",
        "cents",
        4800,
    ),
    Case(
        "january_net",
        "What are completed January 2026 net signed cents?",
        "SELECT COALESCE(SUM(quantity * unit_price_cents - "
        f"COALESCE(discount_cents, 0)), 0) AS total FROM data WHERE {JANUARY}",
        "cents",
        4600,
    ),
    Case(
        "january_orders",
        "How many distinct completed orders are in January 2026?",
        f"SELECT COUNT(DISTINCT order_id) AS total FROM data WHERE {JANUARY}",
        "orders",
        4,
    ),
    Case(
        "january_units",
        "What is the signed completed unit count in January 2026?",
        f"SELECT SUM(quantity) AS total FROM data WHERE {JANUARY}",
        "units",
        6,
    ),
    Case(
        "january_missing_discount",
        "How many completed January 2026 lines lack a discount?",
        f"SELECT COUNT(*) AS total FROM data WHERE {JANUARY} "
        "AND discount_cents IS NULL",
        "lines",
        2,
    ),
    Case(
        "march_net",
        "What are completed March 2026 net signed cents, including an empty month?",
        "SELECT COALESCE(SUM(quantity * unit_price_cents - "
        "COALESCE(discount_cents, 0)), 0) "
        "AS total FROM data WHERE status = 'completed' "
        "AND CAST(ordered_on AS DATE) >= DATE '2026-03-01' "
        "AND CAST(ordered_on AS DATE) < DATE '2026-04-01'",
        "cents",
        0,
    ),
)


def encoded(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, ensure_ascii=True, indent=2) + "\n"
    ).encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def ontology() -> bytes:
    sections = [
        f"schema_version = 1\n[notes]\nconventions = {json.dumps(CONVENTIONS)}\n"
    ]
    for case in CASES:
        values: dict[str, object] = {
            "backend": "parquet",
            "source": "fixture",
            "paths": ["lines.parquet"],
            "description": case.question,
            "grain": "one total",
            "units": case.units,
            "timezone": "UTC",
            "owner": "synthetic-development",
            "expected_columns": ["total"],
            "sql": case.sql,
        }
        sections.append(f"[metrics.{case.id}]\nreviewed_on = 2026-09-09\n")
        sections.extend(
            f"{key} = {json.dumps(value)}\n" for key, value in values.items()
        )
    return "".join(sections).encode()


def server_config(pack: Path, mode: Mode) -> bytes:
    text = 'access_mode = "analysis"\nmax_result_bytes = 12000\n'
    if mode == "promoted":
        text += (
            f"ontology_file = {json.dumps(str(pack / 'ontology' / 'manifest.toml'))}\n"
        )
    text += f"[parquet.fixture]\npath = {json.dumps(str(pack / 'data'))}\n"
    text += "writable = false\n"
    return text.encode()


def text_files(pack: Path) -> dict[str, bytes]:
    return {
        "ontology/manifest.toml": ontology(),
        "golden/cases.json": encoded(
            {
                "schema_version": 1,
                "independent_review_verified": False,
                "conventions": CONVENTIONS,
                "cases": [asdict(case) for case in CASES],
            }
        ),
        **{f"{mode}.toml": server_config(pack, mode) for mode in MODES},
    }


def private_directory(path: Path) -> None:
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError("Use an absolute path without symlinks")
    info = path.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Use an existing private owned directory")


def write_new(path: Path, raw: bytes) -> None:
    with path.open("xb") as handle:
        os.fchmod(handle.fileno(), 0o600)
        handle.write(raw)


def create_pack(output_root: Path) -> dict[str, str]:
    """Create a new UUID pack without overwriting or inspecting other source data."""
    private_directory(output_root)
    pack = output_root / uuid4().hex
    pack.mkdir(mode=0o700)
    for name in ("data", "ontology", "golden"):
        (pack / name).mkdir(mode=0o700)
    parquet = pack / "data" / "lines.parquet"
    table = pa.Table.from_pylist([dict(zip(COLUMNS, row, strict=True)) for row in ROWS])
    pq.write_table(table, parquet)
    parquet.chmod(0o600)
    files = text_files(pack)
    for name, raw in files.items():
        write_new(pack / name, raw)
    files["data/lines.parquet"] = parquet.read_bytes()
    manifest = encoded(
        {
            "schema_version": 1,
            "kind": "synthetic_order_lines_v1",
            "files": {name: digest(raw) for name, raw in files.items()},
            "semantic_revision": digest(files["ontology/manifest.toml"]),
            "independent_review_verified": False,
            "source_snapshot_verified": False,
            "model_quality_measured": False,
        }
    )
    write_new(pack / "manifest.json", manifest)
    return {"pack": str(pack), "manifest_sha256": digest(manifest)}


def read_private(path: Path) -> bytes:
    # Fixed children of a validated private directory. This is not an OS sandbox
    # against an owner concurrently replacing paths or rewriting data.
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_nlink != 1
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("Invalid private fixture file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("Fixture file exceeds limit")
    return raw


def check_pack(pack: Path, manifest_sha256: str) -> str:
    """Check a caller-pinned manifest and this version's fixed configs and labels."""
    private_directory(pack)
    for directory in ("data", "ontology", "golden"):
        private_directory(pack / directory)
    expected_text = text_files(pack)
    names = {*expected_text, "data/lines.parquet"}
    expected_children = {
        "data",
        "ontology",
        "golden",
        "raw.toml",
        "promoted.toml",
        "manifest.json",
    }
    if {p.name for p in pack.iterdir()} != expected_children:
        raise ValueError("Unexpected fixture contents")
    for directory in ("data", "ontology", "golden"):
        if {f"{directory}/{p.name}" for p in (pack / directory).iterdir()} != {
            name for name in names if name.startswith(directory + "/")
        }:
            raise ValueError("Unexpected fixture contents")
    manifest = read_private(pack / "manifest.json")
    if digest(manifest) != manifest_sha256:
        raise ValueError("Fixture manifest digest changed")
    files = {name: read_private(pack / name) for name in names}
    if any(files[name] != raw for name, raw in expected_text.items()):
        raise ValueError("Fixture definitions differ from this packaged version")
    revision = digest(files["ontology/manifest.toml"])
    expected_manifest = encoded(
        {
            "schema_version": 1,
            "kind": "synthetic_order_lines_v1",
            "files": {name: digest(raw) for name, raw in files.items()},
            "semantic_revision": revision,
            "independent_review_verified": False,
            "source_snapshot_verified": False,
            "model_quality_measured": False,
        }
    )
    if manifest != expected_manifest:
        raise ValueError("Fixture contents changed")
    return revision


async def verify_pack(pack: Path, manifest_sha256: str) -> dict[str, Any]:
    revision = check_pack(pack, manifest_sha256)
    checked = 0
    for mode in MODES:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "data_mcp.cli", "--config", str(pack / f"{mode}.toml")],
        )
        async with Client(params) as client:
            listed = await client.list_tools()
            tools = {tool.name for tool in listed.tools}
            if tools & {"write_parquet", "execute_postgres"}:
                raise ValueError("Fixture server exposed writes")
            if mode == "raw" and tools & {
                "get_semantic_context",
                "list_metrics",
                "run_metric",
            }:
                raise ValueError("Raw fixture exposed semantics")
            for case in CASES:
                arguments = (
                    {"root": "fixture", "paths": ["lines.parquet"], "sql": case.sql}
                    if mode == "raw"
                    else {"name": case.id, "revision": revision}
                )
                result = await client.call_tool(
                    "query_parquet" if mode == "raw" else "run_metric", arguments
                )
                content = result.structured_content
                if (
                    result.is_error
                    or content is None
                    or content.get("columns") != ["total"]
                    or content.get("rows") != [[case.expected]]
                    or type(content["rows"][0][0]) is not int
                    or content.get("truncated") is not False
                ):
                    raise ValueError("Fixture answer mismatch")
                if mode == "promoted" and (
                    content.get("revision") != revision
                    or content.get("units") != case.units
                ):
                    raise ValueError("Fixture attribution mismatch")
                checked += 1
    check_pack(pack, manifest_sha256)
    return {
        "case_count": len(CASES),
        "checked_answers": checked,
        "manifest_sha256": manifest_sha256,
        "file_hashes_match_before_and_after": True,
        "source_snapshot_verified": False,
        "independent_review_verified": False,
        "model_quality_measured": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("create")
    create.add_argument("--output-root", type=Path, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("--pack", type=Path, required=True)
    verify.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args()
    try:
        result = (
            create_pack(args.output_root)
            if args.command == "create"
            else asyncio.run(verify_pack(args.pack, args.manifest_sha256))
        )
    except Exception:
        print(
            "Fixture operation failed; check private files, digest and installation.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
