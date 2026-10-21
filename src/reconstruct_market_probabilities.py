"""Reconstruct the frozen 2022 and 2024 Senate market probabilities.

Run from the repository root:
    python src/reconstruct_market_probabilities.py
    python src/reconstruct_market_probabilities.py \
        --csv outputs/tables/rebuilt_market_probabilities.csv

The raw upstream files are not vendored. The script retrieves the exact files
named in ``data/raw/market_sources.json`` (or accepts local pinned checkouts),
verifies every Git blob SHA, applies the frozen time/contract normalization,
and only then compares the rebuilt probabilities with the committed
common-support tables.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import date, datetime, time, timezone
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
DEFAULT_MANIFEST = ROOT / "data" / "raw" / "market_sources.json"
DEFAULT_CACHE = ROOT / ".cache" / "market_sources"

HORIZONS = (60, 30, 14, 7)
EXPECTED_COUNTS = {2022: 34, 2024: 60}
EXPECTED_HORIZON_COUNTS = {
    2022: {60: 7, 30: 8, 14: 9, 7: 10},
    2024: {60: 12, 30: 17, 14: 15, 7: 16},
}
EXPECTED_RACE_COUNTS = {2022: 10, 2024: 18}
PROBABILITY_TOLERANCE = 1e-12
GRID_TOLERANCE_SECONDS = 60
MAX_DOWNLOAD_BYTES = 25_000_000
USER_AGENT = "senate-polling-prediction-markets/market-reproduction"

OUTPUT_FIELDS = (
    "polling_signal_id",
    "cycle",
    "state",
    "horizon_days",
    "cutoff_date",
    "sample_status",
    "market_target_timestamp_utc",
    "market_source_timestamp_utc",
    "market_age_hours",
    "p_market_dem",
    "source_repository",
    "source_commit",
    "source_file",
    "source_git_blob_sha",
    "source_record_locator",
    "source_outcome",
    "source_price",
    "source_amount",
    "source_shares",
    "normalization_rule",
)


def git_blob_sha(payload: bytes) -> str:
    """Return the Git object ID for raw file bytes."""
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _safe_relative_path(value: str) -> PurePosixPath:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or "\\" in value
            or any(part in ("", ".", "..") for part in path.parts)):
        raise ValueError(f"Unsafe source path in manifest: {value!r}")
    return path


def _validate_sha(value: str, label: str) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", value):
        raise ValueError(f"Invalid 40-character Git SHA for {label}: {value!r}")


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    """Load and validate the checksum-pinned upstream-source manifest."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Expected market source manifest schema_version=1")
    sources = manifest.get("sources")
    if not isinstance(sources, dict) or set(sources) != {"2022", "2024"}:
        raise ValueError("Market source manifest must contain only 2022 and 2024")

    for cycle, source in sources.items():
        repository = source.get("repository", "")
        if repository.count("/") != 1 or any(not part for part in repository.split("/")):
            raise ValueError(f"Invalid repository for {cycle}: {repository!r}")
        _validate_sha(source.get("commit", ""), f"{cycle} commit")
        if source.get("license_file_at_pinned_commit") is not None:
            raise ValueError(
                f"Update the documented redistribution review before vendoring {cycle} data"
            )
        if source.get("redistribution_policy") != "upstream_only_not_vendored":
            raise ValueError(f"Unexpected redistribution policy for {cycle}")

        files = source.get("files")
        if not isinstance(files, list) or not files:
            raise ValueError(f"No source files declared for {cycle}")
        seen_paths = set()
        seen_states = set()
        for entry in files:
            source_path = str(_safe_relative_path(entry.get("path", "")))
            if source_path in seen_paths:
                raise ValueError(f"Duplicate source path for {cycle}: {source_path}")
            seen_paths.add(source_path)
            _validate_sha(entry.get("git_blob_sha", ""), source_path)
            if cycle == "2022":
                state = entry.get("state", "")
                if not state or state in seen_states:
                    raise ValueError(f"Invalid or duplicate 2022 source state: {state!r}")
                seen_states.add(state)

    if len(sources["2024"]["files"]) != 1:
        raise ValueError("Expected one frozen 2024 CLOB-history archive")
    return manifest


def load_common_support(year: int, path: Path) -> list[dict[str, str]]:
    """Load target metadata and frozen market values used only for regression checks."""
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {
            "polling_signal_id", "state", "horizon_days", "cutoff_date",
            "p_market_dem",
        }
        if year == 2022:
            required.update({
                "sample_status", "market_source_file", "market_source_blob_sha",
            })
        elif year == 2024:
            required.add("market_observed_timestamp_utc")
        else:
            raise ValueError(f"Unsupported common-support year: {year}")
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{year} common-support CSV missing columns: {sorted(missing)}")
        rows = list(reader)

    ids = [row["polling_signal_id"] for row in rows]
    if len(rows) != EXPECTED_COUNTS[year] or len(ids) != len(set(ids)):
        raise ValueError(
            f"Expected {EXPECTED_COUNTS[year]} unique {year} common-support rows"
        )
    if len({row["state"] for row in rows}) != EXPECTED_RACE_COUNTS[year]:
        raise ValueError(f"Unexpected {year} common-support race count")
    horizons = Counter(int(row["horizon_days"]) for row in rows)
    if dict(horizons) != EXPECTED_HORIZON_COUNTS[year]:
        raise ValueError(f"Unexpected {year} horizon counts: {dict(horizons)}")

    for row in rows:
        horizon = int(row["horizon_days"])
        expected_id = (
            f"{year}-{row['state'].lower().replace(' ', '-')}-{horizon}d"
        )
        if row["polling_signal_id"] != expected_id:
            raise ValueError(f"Inconsistent common-support ID: {row['polling_signal_id']}")
        date.fromisoformat(row["cutoff_date"])
        probability = float(row["p_market_dem"])
        if not math.isfinite(probability) or not 0.0 < probability < 1.0:
            raise ValueError(f"Invalid frozen market probability: {row['polling_signal_id']}")
        if year == 2022 and row["sample_status"] != "PRIMARY_2022":
            raise ValueError("Only PRIMARY_2022 rows may enter the development market sample")
    return rows


def validate_manifest_lineage(manifest: dict, targets_2022: list[dict[str, str]]) -> None:
    """Tie the 2022 per-market manifest entries to committed row provenance."""
    source = manifest["sources"]["2022"]
    by_state = {entry["state"]: entry for entry in source["files"]}
    if set(by_state) != {row["state"] for row in targets_2022}:
        raise ValueError("2022 manifest state set differs from common-support targets")

    observed_counts = Counter(row["state"] for row in targets_2022)
    for row in targets_2022:
        entry = by_state[row["state"]]
        if (row["market_source_file"] != entry["path"]
                or row["market_source_blob_sha"] != entry["git_blob_sha"]):
            raise ValueError(
                f"2022 source lineage changed for {row['polling_signal_id']}"
            )
    for state, entry in by_state.items():
        if entry.get("common_support_observations") != observed_counts[state]:
            raise ValueError(f"2022 manifest observation count changed for {state}")
    if (manifest["sources"]["2024"]["files"][0].get("common_support_observations")
            != EXPECTED_COUNTS[2024]):
        raise ValueError("2024 manifest observation count changed")


def _raw_url(repository: str, commit: str, source_path: str) -> str:
    quoted_path = urllib.parse.quote(source_path, safe="/")
    return f"https://raw.githubusercontent.com/{repository}/{commit}/{quoted_path}"


def _verify_payload(payload: bytes, expected_sha: str, label: str) -> None:
    actual_sha = git_blob_sha(payload)
    if actual_sha != expected_sha:
        raise ValueError(
            f"Git blob SHA mismatch for {label}: expected {expected_sha}, got {actual_sha}"
        )


def _download(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/octet-stream"},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            payload = response.read(MAX_DOWNLOAD_BYTES + 1)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Could not retrieve pinned market source {url}. "
            "Retry online or supply the documented local-source override."
        ) from error
    if len(payload) > MAX_DOWNLOAD_BYTES:
        raise ValueError(f"Refusing unexpectedly large market source: {url}")
    return payload


def acquire_source(
    *,
    cycle: int,
    source: dict,
    file_entry: dict,
    cache_dir: Path,
    offline: bool,
    local_path: Path | None = None,
) -> tuple[bytes, str]:
    """Read a local override/cache or download one verified upstream file."""
    source_path = str(_safe_relative_path(file_entry["path"]))
    expected_sha = file_entry["git_blob_sha"]
    label = f"{source['repository']}@{source['commit']}:{source_path}"

    if local_path is not None:
        payload = local_path.read_bytes()
        _verify_payload(payload, expected_sha, label)
        return payload, "local_override"

    cached_path = cache_dir / f"{cycle}-{source['commit'][:12]}" / Path(*PurePosixPath(source_path).parts)
    if cached_path.exists():
        payload = cached_path.read_bytes()
        _verify_payload(payload, expected_sha, label)
        return payload, "verified_cache"
    if offline:
        raise FileNotFoundError(
            f"Pinned source is absent from the offline cache: {cached_path}"
        )

    payload = _download(_raw_url(source["repository"], source["commit"], source_path))
    _verify_payload(payload, expected_sha, label)
    cached_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = cached_path.with_suffix(cached_path.suffix + ".tmp")
    temporary_path.write_bytes(payload)
    temporary_path.replace(cached_path)
    return payload, "downloaded"


def _parse_optional_float(value: str | None, label: str) -> float | None:
    if value is None or value.strip() == "":
        return None
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"Non-finite numeric value in {label}: {value!r}")
    return parsed


def parse_2022_trades(payload: bytes, source_path: str) -> list[dict]:
    """Parse one upstream trade CSV without assigning a source timezone."""
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    required = {"Timestamp", "Outcome", "Price", "Amount", "Shares"}
    missing = required - set(reader.fieldnames or ())
    if missing:
        raise ValueError(f"2022 trade CSV {source_path} missing columns: {sorted(missing)}")

    trades = []
    for source_row, row in enumerate(reader, start=2):
        try:
            observed = datetime.strptime(
                row["Timestamp"].strip(), "%Y-%m-%d %H:%M:%S"
            ).replace(tzinfo=timezone.utc)
        except ValueError as error:
            raise ValueError(
                f"Invalid timezone-naive Timestamp in {source_path} row {source_row}"
            ) from error
        outcome = row["Outcome"].strip()
        if outcome not in {"Democrat", "Republican"}:
            raise ValueError(f"Unexpected contract outcome in {source_path} row {source_row}")
        price = _parse_optional_float(row["Price"], f"{source_path} row {source_row} Price")
        if price is None or not 0.0 <= price <= 1.0:
            raise ValueError(f"Invalid contract price in {source_path} row {source_row}")
        trades.append({
            "source_row": source_row,
            "observed_timestamp": observed,
            "outcome": outcome,
            "price": price,
            "amount": _parse_optional_float(
                row["Amount"], f"{source_path} row {source_row} Amount"
            ),
            "shares": _parse_optional_float(
                row["Shares"], f"{source_path} row {source_row} Shares"
            ),
        })
    if not trades:
        raise ValueError(f"No trades found in {source_path}")
    return trades


def target_noon_utc(cutoff_date: str) -> datetime:
    return datetime.combine(date.fromisoformat(cutoff_date), time(12), timezone.utc)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_2022_trade(trades: list[dict], target: datetime) -> dict:
    """Choose the latest eligible trade; lowest source row wins timestamp ties."""
    eligible = [trade for trade in trades if trade["observed_timestamp"] <= target]
    if not eligible:
        raise ValueError(f"No 2022 trade exists at or before {format_utc(target)}")
    return max(
        eligible,
        key=lambda trade: (trade["observed_timestamp"], -trade["source_row"]),
    )


def reconstruct_2022(
    targets: list[dict[str, str]],
    source: dict,
    payloads: dict[str, bytes],
) -> tuple[list[dict], int]:
    """Rebuild 2022 Democratic probabilities from the raw trade archive."""
    entries_by_state = {entry["state"]: entry for entry in source["files"]}
    parsed_by_path = {
        source_path: parse_2022_trades(payload, source_path)
        for source_path, payload in payloads.items()
    }
    raw_trade_rows = sum(len(trades) for trades in parsed_by_path.values())

    rebuilt = []
    for target_row in targets:
        entry = entries_by_state[target_row["state"]]
        source_path = entry["path"]
        target = target_noon_utc(target_row["cutoff_date"])
        selected = select_2022_trade(parsed_by_path[source_path], target)
        probability = (
            selected["price"]
            if selected["outcome"] == "Democrat"
            else 1.0 - selected["price"]
        )
        rebuilt.append({
            "polling_signal_id": target_row["polling_signal_id"],
            "cycle": 2022,
            "state": target_row["state"],
            "horizon_days": int(target_row["horizon_days"]),
            "cutoff_date": target_row["cutoff_date"],
            "sample_status": target_row["sample_status"],
            "market_target_timestamp_utc": format_utc(target),
            "market_source_timestamp_utc": format_utc(selected["observed_timestamp"]),
            "market_age_hours": (
                target - selected["observed_timestamp"]
            ).total_seconds() / 3600.0,
            "p_market_dem": probability,
            "source_repository": source["repository"],
            "source_commit": source["commit"],
            "source_file": source_path,
            "source_git_blob_sha": entry["git_blob_sha"],
            "source_record_locator": f"csv_row:{selected['source_row']}",
            "source_outcome": selected["outcome"],
            "source_price": selected["price"],
            "source_amount": selected["amount"],
            "source_shares": selected["shares"],
            "normalization_rule": (
                "timezone-naive timestamp treated as UTC; last trade at/before "
                "target; first source row breaks timestamp ties; "
                "Democrat=price, Republican=1-price"
            ),
        })
    return rebuilt, raw_trade_rows


def parse_2024_archive(payload: bytes) -> tuple[dict[str, list[dict]], int]:
    """Validate the archived Polymarket CLOB price-history response."""
    archive = json.loads(payload.decode("utf-8"))
    if not isinstance(archive, dict) or not archive:
        raise ValueError("2024 market archive must be a non-empty state mapping")

    normalized = {}
    total_points = 0
    for state, samples in archive.items():
        if not isinstance(state, str) or not isinstance(samples, list) or not samples:
            raise ValueError(f"Invalid 2024 CLOB series for {state!r}")
        checked = []
        previous_timestamp = None
        for index, sample in enumerate(samples):
            if not isinstance(sample, dict) or not {"t", "p"}.issubset(sample):
                raise ValueError(f"Invalid 2024 CLOB observation for {state} index {index}")
            timestamp = sample["t"]
            probability = float(sample["p"])
            if (not isinstance(timestamp, int)
                    or previous_timestamp is not None and timestamp <= previous_timestamp):
                raise ValueError(f"Non-increasing 2024 timestamp for {state} index {index}")
            if not math.isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise ValueError(f"Invalid 2024 probability for {state} index {index}")
            checked.append({"t": timestamp, "p": probability})
            previous_timestamp = timestamp
        normalized[state] = checked
        total_points += len(checked)
    return normalized, total_points


def select_2024_observation(
    samples: list[dict],
    target: datetime,
    *,
    tolerance_seconds: int = GRID_TOLERANCE_SECONDS,
) -> tuple[int, dict]:
    """Choose the archived point nearest the scheduled noon grid timestamp."""
    target_epoch = int(target.timestamp())
    index, selected = min(
        enumerate(samples),
        key=lambda item: (abs(item[1]["t"] - target_epoch), item[0]),
    )
    if abs(selected["t"] - target_epoch) > tolerance_seconds:
        raise ValueError(
            f"No 2024 CLOB grid point within {tolerance_seconds}s of {format_utc(target)}"
        )
    return index, selected


def reconstruct_2024(
    targets: list[dict[str, str]],
    source: dict,
    file_entry: dict,
    payload: bytes,
) -> tuple[list[dict], dict]:
    """Rebuild 2024 Democratic probabilities from the archived CLOB grid."""
    archive, total_points = parse_2024_archive(payload)
    target_states = {row["state"] for row in targets}
    missing_states = target_states - set(archive)
    if missing_states:
        raise ValueError(f"2024 CLOB archive missing target states: {sorted(missing_states)}")

    rebuilt = []
    offsets = []
    for target_row in targets:
        target = target_noon_utc(target_row["cutoff_date"])
        source_index, selected = select_2024_observation(
            archive[target_row["state"]], target
        )
        observed = datetime.fromtimestamp(selected["t"], tz=timezone.utc)
        offsets.append(selected["t"] - int(target.timestamp()))
        rebuilt.append({
            "polling_signal_id": target_row["polling_signal_id"],
            "cycle": 2024,
            "state": target_row["state"],
            "horizon_days": int(target_row["horizon_days"]),
            "cutoff_date": target_row["cutoff_date"],
            "sample_status": "PRIMARY_2024",
            "market_target_timestamp_utc": format_utc(target),
            "market_source_timestamp_utc": format_utc(observed),
            "market_age_hours": (target - observed).total_seconds() / 3600.0,
            "p_market_dem": selected["p"],
            "source_repository": source["repository"],
            "source_commit": source["commit"],
            "source_file": file_entry["path"],
            "source_git_blob_sha": file_entry["git_blob_sha"],
            "source_record_locator": (
                f"json_state:{target_row['state']};array_index_zero_based:{source_index}"
            ),
            "source_outcome": "Democratic contract probability",
            "source_price": selected["p"],
            "source_amount": None,
            "source_shares": None,
            "normalization_rule": (
                "nearest archived CLOB prices-history point to scheduled noon UTC; "
                f"maximum allowed offset {GRID_TOLERANCE_SECONDS}s; price is Democratic probability"
            ),
        })
    return rebuilt, {
        "archive_states": len(archive),
        "archive_price_points": total_points,
        "selected_offset_seconds": sorted(set(offsets)),
    }


def verify_frozen(
    rebuilt: list[dict],
    references: dict[int, list[dict[str, str]]],
    *,
    tolerance: float = PROBABILITY_TOLERANCE,
) -> dict:
    """Regression-check rebuilt values after, never during, source normalization."""
    by_id = {row["polling_signal_id"]: row for row in rebuilt}
    if len(by_id) != len(rebuilt):
        raise AssertionError("Duplicate reconstructed market signal IDs")

    max_difference_by_cycle = {}
    checked = 0
    for year, rows in references.items():
        reference_ids = {row["polling_signal_id"] for row in rows}
        rebuilt_ids = {row["polling_signal_id"] for row in rebuilt if row["cycle"] == year}
        if reference_ids != rebuilt_ids:
            missing = sorted(reference_ids - rebuilt_ids)
            extra = sorted(rebuilt_ids - reference_ids)
            raise AssertionError(
                f"{year} market membership changed: missing={missing}, extra={extra}"
            )
        max_difference = 0.0
        for reference in rows:
            signal_id = reference["polling_signal_id"]
            observed = by_id[signal_id]
            if (observed["state"] != reference["state"]
                    or observed["horizon_days"] != int(reference["horizon_days"])
                    or observed["cutoff_date"] != reference["cutoff_date"]):
                raise AssertionError(f"Market target metadata mismatch: {signal_id}")
            difference = abs(observed["p_market_dem"] - float(reference["p_market_dem"]))
            max_difference = max(max_difference, difference)
            if difference > tolerance:
                raise AssertionError(
                    f"Frozen market-probability mismatch for {signal_id}: {difference}"
                )
            if year == 2022:
                if (observed["source_file"] != reference["market_source_file"]
                        or observed["source_git_blob_sha"]
                        != reference["market_source_blob_sha"]):
                    raise AssertionError(f"Frozen 2022 source lineage mismatch: {signal_id}")
            else:
                if (observed["market_source_timestamp_utc"]
                        != reference["market_observed_timestamp_utc"]):
                    raise AssertionError(
                        f"Frozen 2024 market timestamp mismatch: {signal_id}"
                    )
            checked += 1
        max_difference_by_cycle[str(year)] = max_difference

    return {
        "common_support_rows_checked": checked,
        "rows_checked_by_cycle": {
            str(year): len(rows) for year, rows in references.items()
        },
        "max_market_probability_abs_difference_by_cycle": max_difference_by_cycle,
        "max_market_probability_abs_difference": max(max_difference_by_cycle.values()),
        "frozen_audit_verified": True,
    }


def run(
    *,
    data_dir: Path = DATA,
    manifest_path: Path = DEFAULT_MANIFEST,
    cache_dir: Path = DEFAULT_CACHE,
    offline: bool = False,
    source_2022_root: Path | None = None,
    source_2024_json: Path | None = None,
) -> tuple[list[dict], dict]:
    """Acquire exact raw sources, reconstruct 94 market inputs and verify them."""
    manifest = load_manifest(manifest_path)
    references = {
        year: load_common_support(year, data_dir / f"{year}_common_support.csv")
        for year in (2022, 2024)
    }
    validate_manifest_lineage(manifest, references[2022])

    source_2022 = manifest["sources"]["2022"]
    payloads_2022 = {}
    retrieval_2022 = Counter()
    for file_entry in source_2022["files"]:
        relative = Path(*PurePosixPath(file_entry["path"]).parts)
        local_path = source_2022_root / relative if source_2022_root else None
        payload, method = acquire_source(
            cycle=2022,
            source=source_2022,
            file_entry=file_entry,
            cache_dir=cache_dir,
            offline=offline,
            local_path=local_path,
        )
        payloads_2022[file_entry["path"]] = payload
        retrieval_2022[method] += 1
    rebuilt_2022, raw_trade_rows = reconstruct_2022(
        references[2022], source_2022, payloads_2022
    )

    source_2024 = manifest["sources"]["2024"]
    file_2024 = source_2024["files"][0]
    payload_2024, retrieval_2024 = acquire_source(
        cycle=2024,
        source=source_2024,
        file_entry=file_2024,
        cache_dir=cache_dir,
        offline=offline,
        local_path=source_2024_json,
    )
    rebuilt_2024, archive_summary = reconstruct_2024(
        references[2024], source_2024, file_2024, payload_2024
    )

    rebuilt = rebuilt_2022 + rebuilt_2024
    verification = verify_frozen(rebuilt, references)
    report = {
        "sources": {
            "2022": {
                "repository": source_2022["repository"],
                "commit": source_2022["commit"],
                "files_verified": len(source_2022["files"]),
                "retrieval_methods": dict(sorted(retrieval_2022.items())),
                "raw_trade_rows": raw_trade_rows,
                "license_file_at_pinned_commit": source_2022[
                    "license_file_at_pinned_commit"
                ],
                "raw_data_vendored": False,
            },
            "2024": {
                "repository": source_2024["repository"],
                "commit": source_2024["commit"],
                "files_verified": 1,
                "retrieval_methods": {retrieval_2024: 1},
                **archive_summary,
                "request_provenance": source_2024["request_provenance"],
                "license_file_at_pinned_commit": source_2024[
                    "license_file_at_pinned_commit"
                ],
                "raw_data_vendored": False,
            },
        },
        "market_probabilities": {
            "total": len(rebuilt),
            "by_cycle": {"2022": len(rebuilt_2022), "2024": len(rebuilt_2024)},
            "by_cycle_and_horizon": {
                str(year): {
                    str(horizon): sum(
                        row["cycle"] == year and row["horizon_days"] == horizon
                        for row in rebuilt
                    )
                    for horizon in HORIZONS
                }
                for year in (2022, 2024)
            },
        },
        "verification": verification,
    }
    return rebuilt, report


def export_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use only verified cache files or explicit local-source overrides",
    )
    parser.add_argument(
        "--source-2022-root",
        type=Path,
        help="Optional local checkout of the pinned 2022 source repository",
    )
    parser.add_argument(
        "--source-2024-json",
        type=Path,
        help="Optional local copy of the pinned 2024 Senate CLOB-history JSON",
    )
    parser.add_argument("--csv", type=Path, help="Optional 94-row normalized output")
    parser.add_argument("--json", type=Path, help="Optional machine-readable audit summary")
    args = parser.parse_args()

    rows, report = run(
        manifest_path=args.manifest,
        cache_dir=args.cache_dir,
        offline=args.offline,
        source_2022_root=args.source_2022_root,
        source_2024_json=args.source_2024_json,
    )
    if args.csv:
        export_csv(args.csv, rows)
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    print(payload, end="")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
