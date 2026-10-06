"""Read-only comparison metrics from durable public telemetry; no adapter dispatch."""

from collections import defaultdict
from datetime import UTC, datetime
from itertools import combinations
from math import ceil, isfinite, log, sqrt
from statistics import mean, median

from sqlalchemy import select

from .experiment_queue import ExperimentQueue
from .persistence import DatabaseStore, EventRow, ExperimentRow, MoveRow
from .tournaments import CHESS_RESULTS, SETTLED, resolve_tournament

USAGE_FIELDS = ("input_tokens", "output_tokens", "reasoning_tokens", "estimated_cost_usd")


def opening_bound(scores: list[float]) -> dict | None:
    """Hoeffding bound conditional on independent, bounded opening-block means."""
    if len(scores) < 2:
        return None
    center = mean(scores)
    radius = sqrt(log(40) / (2 * len(scores)))
    return {
        "low": max(0.0, center - radius),
        "high": min(1.0, center + radius),
        "level": 0.95,
        "method": "opening-block-hoeffding-95-v1",
    }


def numeric(value):
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(value)
        and value >= 0
    )


def new_row(variant, config):
    player = variant["player"]
    return {
        "key": variant["key"],
        "entrant": variant["entrant"],
        "effort": player["effort"],
        "provider": player["provider"],
        "model": player["model"],
        "division": player["division"],
        "profile_hash": variant["profile_hash"],
        "provider_effort": variant.get("provider_effort"),
        "pool": (
            f"{player['division']}|{config['initial_time_ms']}+{config['increment_ms']}"
            f"|{player['protocol_version']}"
        ),
        "games": {
            k: 0
            for k in [
                "scheduled",
                "started",
                "settled",
                "chess_completed",
                "wins",
                "draws",
                "losses",
                "limited",
                "failed",
                "cancelled",
                "pending",
            ]
        },
        "strength": {
            "score_points": 0.0,
            "score_rate": None,
            "opening_blocks": 0,
            "opening_mean": None,
            "interval": None,
            "interval_unavailable_reason": None,
        },
        "reliability": {"agent_failure_events": 0, "illegal_move_events": 0, "timeouts": 0},
        "efficiency": {
            "accepted_moves": 0,
            "retries_observed": 0,
            "latency_ms": {},
            "usage": {
                k: {"total": None, "observed_moves": 0, "missing_moves": 0} for k in USAGE_FIELDS
            },
        },
    }


def effort_response(rows, cohorts, knockout, mixed, complete_run=True):
    comparisons = []
    for left, right in combinations(rows.values(), 2):
        if left["entrant"] != right["entrant"]:
            continue
        a, b = cohorts[left["key"]], cohorts[right["key"]]
        common = set(a) & set(b)
        differences = defaultdict(list)
        incomplete = False
        incomplete_openings = set()
        for condition in sorted(common):
            values_a, values_b = a[condition], b[condition]
            if len(values_a) != len(values_b) or any(v is None for v in values_a + values_b):
                incomplete = True
                incomplete_openings.add(condition[1])
                continue
            differences[condition[1]].append(mean(values_b) - mean(values_a))
        block_differences = [
            mean(values)
            for opening, values in differences.items()
            if opening not in incomplete_openings
        ]
        reason = (
            "Knockout opponents are adaptive."
            if knockout
            else "Mixed rating pools cannot support this interval."
            if mixed
            else "Opponent, opening, repetition and color conditions must match."
            if (not common or set(a) != set(b))
            else "The full run must finish with chess results before inference."
            if not complete_run
            else "Every matched game must have a completed chess result."
            if incomplete
            else "At least two distinct matched opening blocks are required."
            if len(block_differences) < 2
            else None
        )
        comparable = not knockout and not mixed and common and set(a) == set(b) and not incomplete
        delta = mean(block_differences) if comparable and block_differences else None
        interval = None
        if reason is None:
            radius = 2 * sqrt(log(40) / (2 * len(block_differences)))
            interval = {
                "low": max(-1.0, delta - radius),
                "high": min(1.0, delta + radius),
                "level": 0.95,
                "method": "paired-opening-hoeffding-95-v1",
            }
        comparisons.append(
            {
                "entrant": left["entrant"],
                "left": left["key"],
                "right": right["key"],
                "matched_blocks": len(block_differences),
                "score_delta": delta,
                "interval": interval,
                "interval_unavailable_reason": reason,
            }
        )
    return comparisons


class ExperimentMetrics:
    def __init__(self, store: DatabaseStore):
        self.store = store

    async def get(self, run_id: str) -> dict:
        run = await ExperimentQueue(self.store).snapshot(run_id)
        async with self.store.sessions() as session:
            experiment = await session.get(ExperimentRow, run["experiment_id"])
            plan = experiment.document
            opponents, _, _ = resolve_tournament(plan, run["jobs"])
            schedule = {g["number"]: g for g in plan["schedule"]}
            rows = {v["key"]: new_row(v, plan["configuration"]) for v in plan["variants"]}
            blocks = defaultdict(lambda: defaultdict(list))
            latencies = defaultdict(list)
            cohorts = defaultdict(lambda: defaultdict(list))
            assigned = {}
            for job in run["jobs"]:
                pair = opponents.get(job["number"])
                if pair is None:
                    continue
                game = schedule[job["number"]]
                assigned[job["id"]] = (pair, game["initial_fen"].split()[1] == "w")
                valid = job["state"] == "completed" and job["result"] in CHESS_RESULTS
                white_score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}.get(job["result"])
                for color, key in enumerate(pair):
                    row, stats = rows[key], rows[key]["games"]
                    stats["scheduled"] += 1
                    stats["started"] += int(job["has_game"])
                    stats["settled"] += int(job["state"] in SETTLED)
                    stats["pending"] += int(job["state"] not in SETTLED)
                    value = (white_score if color == 0 else 1 - white_score) if valid else None
                    opponent = pair[1 - color]
                    if rows[opponent]["entrant"] != row["entrant"]:
                        condition = (opponent, game["initial_fen"], game["repetition"], color)
                        cohorts[key][condition].append(value)
                    if valid:
                        stats["chess_completed"] += 1
                        stats["wins" if value == 1 else "losses" if value == 0 else "draws"] += 1
                        row["strength"]["score_points"] += value
                        blocks[key][game["initial_fen"]].append(value)
                    elif job["result"] == "limited":
                        stats["limited"] += 1
                    elif job["state"] in {"failed", "cancelled"}:
                        stats[job["state"]] += 1

            def player_for(match_id, ply):
                pair, starts_white = assigned[match_id]
                return pair[0 if ((ply % 2 == 1) == starts_white) else 1]

            if assigned:
                moves = await session.stream(
                    select(MoveRow.match_id, MoveRow.ply, MoveRow.player_metadata)
                    .where(MoveRow.match_id.in_(assigned))
                    .execution_options(yield_per=500)
                )
                async for match_id, ply, metadata in moves:
                    key = player_for(match_id, ply)
                    efficiency = rows[key]["efficiency"]
                    efficiency["accepted_moves"] += 1
                    metadata = metadata if isinstance(metadata, dict) else {}
                    latency = metadata.get("latency_ms")
                    if numeric(latency):
                        latencies[key].append(latency)
                    attempt = metadata.get("attempt")
                    if isinstance(attempt, int) and 1 <= attempt <= 1000:
                        efficiency["retries_observed"] += attempt - 1
                    usage = metadata.get("usage") or {}
                    usage = usage if isinstance(usage, dict) else {}
                    for field in USAGE_FIELDS:
                        summary = efficiency["usage"][field]
                        value = usage.get(field)
                        if numeric(value):
                            summary["total"] = (summary["total"] or 0) + value
                            summary["observed_moves"] += 1
                        else:
                            summary["missing_moves"] += 1
                events = await session.stream(
                    select(
                        EventRow.match_id,
                        EventRow.position_version,
                        EventRow.event_type,
                        EventRow.payload,
                    )
                    .where(
                        EventRow.match_id.in_(assigned),
                        EventRow.event_type.in_(["agent.failed", "clock.timeout"]),
                    )
                    .execution_options(yield_per=500)
                )
                async for match_id, version, event_type, payload in events:
                    key = player_for(match_id, version + 1)
                    if event_type == "clock.timeout":
                        color = payload.get("color")
                        if color not in {"white", "black"}:
                            continue
                        key = assigned[match_id][0][0 if color == "white" else 1]
                        rows[key]["reliability"]["timeouts"] += 1
                    else:
                        rows[key]["reliability"]["agent_failure_events"] += 1
                        rows[key]["reliability"]["illegal_move_events"] += int(
                            payload.get("reason") == "illegal_move"
                        )

        complete_run = run["state"] == "completed" and all(
            job["state"] == "completed" and job["result"] in CHESS_RESULTS for job in run["jobs"]
        )
        mixed = len({r["pool"] for r in rows.values()}) > 1
        knockout = plan.get("tournament", {}).get("format") == "knockout"
        for key, row in rows.items():
            games, strength = row["games"], row["strength"]
            completed = games["chess_completed"]
            strength["score_rate"] = strength["score_points"] / completed if completed else None
            block_means = [mean(values) for values in blocks[key].values()]
            strength["opening_blocks"] = len(block_means)
            strength["opening_mean"] = mean(block_means) if block_means else None
            reason = (
                "Adaptive knockout opponents do not support this fixed-schedule interval."
                if knockout
                else "Mixed rating pools are exhibition comparisons."
                if mixed
                else "Every scheduled game must finish with a chess result."
                if (not games["scheduled"] or completed != games["scheduled"])
                else "At least two distinct opening positions are required."
                if len(block_means) < 2
                else None
            )
            strength["interval_unavailable_reason"] = reason
            if reason is None:
                strength["interval"] = opening_bound(block_means)
            values = sorted(latencies[key])
            row["efficiency"]["latency_ms"] = {
                "count": len(values),
                "mean": mean(values) if values else None,
                "p50": median(values) if values else None,
                "p95": values[ceil(0.95 * len(values)) - 1] if values else None,
            }
        groups = defaultdict(list)
        for row in rows.values():
            groups[row["entrant"]].append(row["key"])
        return {
            "schema_version": "1.0",
            "run_id": run_id,
            "experiment_id": run["experiment_id"],
            "configuration_hash": plan["configuration_hash"],
            "run_state": run["state"],
            "source_revision": run["revision"],
            "generated_at": datetime.now(UTC).isoformat(),
            "unresolved_slots": len(run["jobs"]) - len(assigned),
            "competitors": list(rows.values()),
            "effort_comparisons": effort_response(rows, cohorts, knockout, mixed, complete_run),
            "effort_groups": [
                {"entrant": key, "variants": values}
                for key, values in groups.items()
                if len(values) > 1
            ],
            "notices": [
                "Scores describe this schedule, not calibrated human Elo or general intelligence.",
                "95% Hoeffding ranges assume independent opening blocks. Repeated games and colors "
                "at the same initial FEN form one block; blocks receive equal weight. "
                "This assumption "
                "is not verified by the app and ranges are not corrected for multiple comparisons.",
                "Latency and usage cover accepted moves only, "
                "not all failed or cancelled requests. "
                "Missing usage/cost stays unknown; partial sums are not total provider bills. "
                "Reasoning tokens may overlap output tokens and are not added to them.",
                "Failure counts affect both competitors' game totals; agent-failure events and "
                "timeouts are attributed to the active seat. Effort comparisons are descriptive, "
                "not proof that a setting caused a strength change.",
                "Live metrics are a read-time snapshot; refresh after the batch settles.",
            ],
        }
