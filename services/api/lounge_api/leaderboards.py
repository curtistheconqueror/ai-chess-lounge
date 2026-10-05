"""Local aggregate comparisons; no names or identity verification inferred."""

import hashlib
import json
from collections import Counter

from sqlalchemy import func, select

from .persistence import ComparisonGameRow, MatchRow

MAX_RECORDS = 5000
IDENTITY_FIELDS = (
    "provider",
    "model",
    "underlying_model",
    "family",
    "version",
    "effort_raw",
    "effort_declared",
    "effort_normalized",
    "effort_setting",
    "access",
    "broker",
    "harness",
    "harness_version",
)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def key(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()[:24]


def exclusion(result, include_forfeits):
    if result["takeover"] or result["consultation"]:
        return "assistance_changed"
    if result["lifecycle"] == "aborted":
        return "aborted"
    if result["lifecycle"] == "adjudicated":
        return "adjudicated"
    if result["lifecycle"] != "completed" or result["result"] not in {"1-0", "0-1", "1/2-1/2"}:
        return "unfinished_or_reset"
    if not include_forfeits and result["status"] in {"resigned", "timeout"}:
        return "forfeit_excluded"
    return None


def identity_group(identity, grouping):
    fields = (
        (*IDENTITY_FIELDS, "observed_models")
        if grouping == "exact"
        else ("provider", "model")
        if grouping == "model"
        else ("provider", "family")
        if grouping == "family" and identity["family"]["value"] is not None
        else ("provider", "family", "model")
        if grouping == "family"
        else ("provider", "model", grouping)
    )
    return {f: identity[f] for f in fields} | {
        "kind": identity["kind"],
        "division": identity["division"],
        "protocol": identity["protocol"],
        "connection_mode": identity["connection_mode"],
        "execution": identity["execution"],
    }


def counts():
    return {
        "total_games": 0,
        "eligible_games": 0,
        "wins": 0,
        "losses": 0,
        "draws": 0,
        "forfeits": 0,
        "excluded": {},
    }


def finish(count):
    n = count["eligible_games"]
    count.update(
        {
            "rate_denominator": n,
            "win_rate": count["wins"] / n if n else None,
            "draw_rate": count["draws"] / n if n else None,
            "loss_rate": count["losses"] / n if n else None,
            "score_rate": (count["wins"] + 0.5 * count["draws"]) / n if n else None,
        }
    )


def add(count, score, reason, forfeit):
    count["total_games"] += 1
    if reason:
        count["excluded"][reason] = count["excluded"].get(reason, 0) + 1
    else:
        count["eligible_games"] += 1
        count["wins" if score == 1 else "losses" if score == 0 else "draws"] += 1
        count["forfeits"] += int(forfeit)


def aggregate(records, *, grouping="exact", filters=None, color=None, include_forfeits=True):
    filters = filters or {}
    rows, pairs = {}, {}
    game_exclusions = Counter()
    selected = 0
    for document, result in records:
        seats, condition = document["seats"], document["conditions"]
        seats = {
            c: {
                **s,
                "observed_models": {
                    "value": result.get("observed_models", {}).get(c) or None,
                    "evidence": "observed_provider_response"
                    if result.get("observed_models", {}).get(c)
                    else "unknown",
                },
            }
            for c, s in seats.items()
        }

        def matches(seat):
            return all(
                (seat[field]["value"] or "unknown") == value for field, value in filters.items()
            )

        if filters and not any(matches(s) for s in seats.values()):
            continue
        selected += 1
        reason = exclusion(result, include_forfeits)
        if any(len(values) > 1 for values in result.get("observed_models", {}).values()):
            reason = reason or "observed_model_changed"
        identities = {c: identity_group(s, grouping) for c, s in seats.items()}
        keys = {c: key({"identity": identities[c], "conditions": condition}) for c in seats}
        if keys["white"] == keys["black"]:
            reason = reason or "same_comparison_group"
        if reason:
            game_exclusions[reason] += 1
        white_score = {"1-0": 1, "0-1": 0, "1/2-1/2": 0.5}.get(result["result"])
        forfeit = result["status"] in {"resigned", "timeout"}
        for seat_color, identity in seats.items():
            if color and seat_color != color:
                continue
            k = keys[seat_color]
            row = rows.setdefault(
                k,
                {
                    "key": k,
                    "identity": identities[seat_color],
                    "conditions": condition,
                    "counts": counts(),
                    "colors": {"white": counts(), "black": counts()},
                    "variants": {},
                    "opt_in_aliases": set(),
                },
            )
            variant = {f: identity[f] for f in (*IDENTITY_FIELDS, "observed_models")}
            row["variants"][key(variant)] = variant
            if identity["listing_alias"]:
                row["opt_in_aliases"].add(identity["listing_alias"])
            score = (
                white_score
                if seat_color == "white"
                else 1 - white_score
                if white_score is not None
                else None
            )
            # A collapsed self-match appears once per selected color, never twice
            # in a combined row. It is excluded from rates regardless of outcome.
            if keys["white"] != keys["black"] or seat_color == (color or "white"):
                add(row["counts"], score, reason, forfeit)
            add(row["colors"][seat_color], score, reason, forfeit)
        # Head-to-head counts describe games, independent of the row color filter.
        if keys["white"] != keys["black"]:
            left, right = sorted(keys.values())
            pair = pairs.setdefault(
                (left, right),
                {
                    "left": left,
                    "right": right,
                    "conditions": condition,
                    "counts": counts(),
                    "left_identity": identities["white" if left == keys["white"] else "black"],
                    "right_identity": identities["white" if right == keys["white"] else "black"],
                },
            )
            score = (
                white_score
                if left == keys["white"]
                else 1 - white_score
                if white_score is not None
                else None
            )
            add(pair["counts"], score, reason, forfeit)
    for row in rows.values():
        finish(row["counts"])
        for c in row["colors"].values():
            finish(c)
        row["variants"] = list(row["variants"].values())
        row["opt_in_aliases"] = sorted(row["opt_in_aliases"])
    for pair in pairs.values():
        finish(pair["counts"])
    return {
        "schema_version": "1.0",
        "grouping": grouping,
        "selected_games": selected,
        "excluded_games": dict(game_exclusions),
        "rows": sorted(
            rows.values(),
            key=lambda r: (
                -(r["counts"]["score_rate"] or 0),
                -r["counts"]["eligible_games"],
                r["key"],
            ),
        ),
        "head_to_head": list(pairs.values()),
        "notices": [
            (
                "Descriptive local results, not calibrated Elo or general intelligence. No "
                "confidence or causal-effort claim."
            ),
            (
                "Rates use eligible games; score = (wins + half draws) / eligible games. Total "
                "includes exclusions; sample sizes are explicit."
            ),
            (
                "Resignation and clock timeout are forfeits, included by default; "
                "aborted/adjudicated/unfinished games and assistance changes are excluded."
            ),
            (
                "Identical collapsed comparison groups are excluded from rates. Grouping can pool "
                "versions/efforts: inspect variants or use Exact."
            ),
            (
                "Filters select games involving at least one matching seat. Row color filters do "
                "not alter head-to-head game counts."
            ),
            (
                "Unknown is not verified. Recorded configuration/adapter mapping does not prove "
                "the provider's underlying model or private subscription settings."
            ),
            (
                "Model aggregates omit player IDs, owners and default display names. Only "
                "explicit opt-in aliases are listed; no owner directory exists."
            ),
        ],
    }


class Leaderboards:
    def __init__(self, store):
        self.store = store

    async def get(self, **options):
        await self.store.initialize()
        async with self.store.sessions() as session:
            records = list(
                await session.scalars(
                    select(ComparisonGameRow)
                    .order_by(ComparisonGameRow.match_id, ComparisonGameRow.generation)
                    .limit(MAX_RECORDS + 1)
                )
            )
            legacy = await session.scalar(
                select(func.count())
                .select_from(MatchRow)
                .where(
                    ~select(ComparisonGameRow.match_id)
                    .where(
                        ComparisonGameRow.match_id == MatchRow.id,
                        ComparisonGameRow.generation == MatchRow.generation,
                    )
                    .exists()
                )
            )
        report = aggregate([(r.identity, r.outcome) for r in records[:MAX_RECORDS]], **options)
        report.update(
            {
                "record_limit": MAX_RECORDS,
                "truncated": len(records) > MAX_RECORDS,
                "legacy_games_without_snapshot": legacy,
                "coverage": (
                    "Per-generation snapshots since this phase; legacy games are retained but "
                    "excluded because original identity is unavailable."
                ),
            }
        )
        return report
