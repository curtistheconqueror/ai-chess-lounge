"""Versioned tournament schedules and deterministic, tournament-local results."""

from itertools import combinations

import chess

CHESS_RESULTS = {"1-0", "0-1", "1/2-1/2"}
SETTLED = {"completed", "failed", "cancelled", "blocked"}


def build_tournament(config: dict, variants: list[dict]) -> tuple[list[dict], dict]:
    keys = [v["key"] for v in variants]
    format_name = config["format"]
    series = []

    def add(a, b, round_number):
        entry = {
            "id": f"s{len(series) + 1}",
            "round": round_number,
            "white": a,
            "black": b,
            "numbers": [],
        }
        series.append(entry)
        return f"winner:{entry['id']}"

    if format_name == "round_robin":
        for a, b in combinations(keys, 2):
            add(a, b, 1)
    elif format_name == "gauntlet":
        if config["anchor"] not in keys:
            raise ValueError("Choose an existing competitor variant as the gauntlet anchor.")
        for key in keys:
            if key != config["anchor"]:
                add(config["anchor"], key, len(series) + 1)
    else:
        if len(keys) & (len(keys) - 1):
            raise ValueError("Knockout requires a power-of-two competitor field (2, 4, 8, 16, 32).")
        round_number = 1
        slots = keys
        while len(slots) > 1:
            slots = [add(slots[i], slots[i + 1], round_number) for i in range(0, len(slots), 2)]
            round_number += 1
    game_count = (
        len(series)
        * len(config["openings"])
        * config["repetitions"]
        * (2 if config["color_swap"] else 1)
    )
    if game_count > 512:
        raise ValueError("Tournament exceeds the 512-game plan limit.")
    schedule = []
    for entry in series:
        for opening_index, opening in enumerate(config["openings"]):
            board = chess.Board()
            for move in opening["moves"]:
                board.push_uci(move)
            for repetition in range(config["repetitions"]):
                sides = [(entry["white"], entry["black"])]
                if config["color_swap"]:
                    sides.append((entry["black"], entry["white"]))
                for white, black in sides:
                    number = len(schedule) + 1
                    entry["numbers"].append(number)
                    schedule.append(
                        {
                            "number": number,
                            "white": white,
                            "black": black,
                            "opening_index": opening_index,
                            "opening": opening["name"],
                            "initial_fen": board.fen(),
                            "repetition": repetition + 1,
                            "series": entry["id"],
                            "round": entry["round"],
                        }
                    )
    return schedule, {
        "format": format_name,
        "series": series,
        "rating_spec": "local-elo-v1",
        "tie_rule": "unresolved",
        "seeding": keys,
    }


def resolve_tournament(plan: dict, jobs: list[dict]) -> tuple[dict, set[int], list[dict]]:
    """Resolve only actual chess winners. No failed/limited game is a chess loss."""
    tournament = plan.get("tournament")
    if not tournament:
        return {g["number"]: (g["white"], g["black"]) for g in plan["schedule"]}, set(), []
    by_number = {j["number"]: j for j in jobs}
    games = {g["number"]: g for g in plan["schedule"]}
    resolved, blocked, standings = {}, set(), []
    winners, unresolved = {}, set()

    def slot(key):
        return winners.get(key.removeprefix("winner:")) if key.startswith("winner:") else key

    for entry in tournament["series"]:
        white, black = slot(entry["white"]), slot(entry["black"])
        parent_blocked = any(
            k.startswith("winner:") and k[7:] in unresolved
            for k in (entry["white"], entry["black"])
        )
        state, winner, score = "pending", None, [0.0, 0.0]
        if parent_blocked:
            blocked.update(entry["numbers"])
            state = "unresolved"
        elif white is not None and black is not None:
            for number in entry["numbers"]:
                game, job = games[number], by_number.get(number, {})
                a, b = slot(game["white"]), slot(game["black"])
                resolved[number] = (a, b)
                if job.get("state") == "completed" and job.get("result") in CHESS_RESULTS:
                    value = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[job["result"]]
                    score[0] += value if a == white else 1 - value
                    score[1] += 1 - value if a == white else value
            if all(by_number.get(n, {}).get("state") in SETTLED for n in entry["numbers"]):
                valid = all(
                    by_number[n].get("state") == "completed"
                    and by_number[n].get("result") in CHESS_RESULTS
                    for n in entry["numbers"]
                )
                if valid:
                    state = "completed"
                    if score[0] != score[1]:
                        winner = white if score[0] > score[1] else black
                        winners[entry["id"]] = winner
                    elif tournament["format"] == "knockout":
                        state = "unresolved"
                else:
                    state = "unresolved"
        if state == "unresolved":
            unresolved.add(entry["id"])
        standings.append(
            {
                "id": entry["id"],
                "round": entry["round"],
                "white": white,
                "black": black,
                "state": state,
                "winner": winner,
                "score": score,
            }
        )
    return resolved, blocked, standings


def tournament_report(plan: dict, jobs: list[dict], run_state: str) -> dict | None:
    if not plan.get("tournament"):
        return None
    opponents, _, series = resolve_tournament(plan, jobs)
    config = plan["configuration"]
    rows = {}
    for variant in plan["variants"]:
        player = variant["player"]
        pool = (
            f"{player['division']}|{config['initial_time_ms']}+{config['increment_ms']}"
            f"|{player['protocol_version']}"
        )
        rows[variant["key"]] = {
            "key": variant["key"],
            "division": player["division"],
            "profile_hash": variant["profile_hash"],
            "pool": pool,
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0.0,
            "no_results": 0,
            "rating": 1500.0,
            "rated_games": 0,
            "rank": 1,
        }
    for job in sorted(jobs, key=lambda j: j["number"]):
        pair = opponents.get(job["number"])
        if pair is None:
            continue
        a, b = (rows[k] for k in pair)
        result = job.get("result")
        if job["state"] != "completed" or result not in CHESS_RESULTS:
            if job["state"] in SETTLED:
                a["no_results"] += 1
                b["no_results"] += 1
            continue
        score = {"1-0": 1.0, "0-1": 0.0, "1/2-1/2": 0.5}[result]
        for row, value in [(a, score), (b, 1 - score)]:
            row["played"] += 1
            row["points"] += value
            row["wins" if value == 1 else "losses" if value == 0 else "draws"] += 1
        if a["pool"] == b["pool"]:
            expected = 1 / (1 + 10 ** ((b["rating"] - a["rating"]) / 400))
            delta = 24 * (score - expected)
            a["rating"] += delta
            b["rating"] -= delta
            a["rated_games"] += 1
            b["rated_games"] += 1
    ordered = sorted(rows.values(), key=lambda r: (r["pool"], -r["points"], r["key"]))
    for pool in {r["pool"] for r in ordered}:
        group = [r for r in ordered if r["pool"] == pool]
        for row in group:
            row["rank"] = 1 + sum(other["points"] > row["points"] for other in group)
            row["rating"] = round(row["rating"], 2)
    format_name = plan["tournament"]["format"]
    terminal = run_state in {"completed", "cancelled", "stopped"}
    champion = series[-1]["winner"] if format_name == "knockout" and series else None
    status = "completed" if terminal else "running"
    if terminal and format_name == "knockout" and champion is None:
        status = "unresolved"
    return {
        "format": format_name,
        "status": status,
        "champion": champion,
        "standings": ordered,
        "series": series,
        "rating_spec": "local-elo-v1",
        "rating_notice": "Tournament-local provisional Elo; not a calibrated human rating. "
        "Only completed chess results within the same pool affect ratings.",
    }
