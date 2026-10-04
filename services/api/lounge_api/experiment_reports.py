"""Bounded, read-only experiment bundles from stable terminal runs."""

import asyncio
import csv
import hashlib
import io
import json
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import chess
import chess.pgn
from sqlalchemy import select

from .experiment_metrics import ExperimentMetrics
from .experiment_queue import ExperimentQueue
from .experiments import canonical_hash
from .persistence import DatabaseStore, ExperimentRow, MatchRow, MoveRow
from .tournaments import CHESS_RESULTS, SETTLED, resolve_tournament

MAX_EXPORT_BYTES = 16 * 1024 * 1024
MAX_EXPORT_MOVES = 25_000
TERMINAL_RUNS = {"completed", "stopped", "cancelled"}
HASH_FIELDS = ("configuration", "variants", "schedule", "game_count", "exhibition", "status")


class ReportConflict(ValueError):
    pass


class ReportTooLarge(ValueError):
    pass


def csv_cell(value):
    if value is None:
        return ""
    if isinstance(value, str) and value.lstrip("".join(map(chr, range(33)))).startswith(
        ("=", "+", "-", "@")
    ):
        return "'" + value
    return value


def csv_bytes(fields, rows) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(fields)
    for row in rows:
        writer.writerow([csv_cell(row.get(key)) for key in fields])
        if output.tell() > MAX_EXPORT_BYTES:
            raise ReportTooLarge("Export exceeds 16 MiB. Use a smaller experiment.")
    return output.getvalue().encode("utf-8")


def json_bytes(value) -> bytes:
    return (
        json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False, allow_nan=False) + "\n"
    ).encode()


def safe_header(value) -> str:
    # PGN tags are quoted lines. Keep public labels from injecting extra headers.
    return str(value).replace("\\", "/").replace('"', "'").replace("\r", " ").replace("\n", " ")


class ExperimentReports:
    def __init__(self, store: DatabaseStore):
        self.store = store

    async def markers(self, ids):
        async with self.store.sessions() as session:
            return list(
                (
                    await session.execute(
                        select(
                            MatchRow.id,
                            MatchRow.generation,
                            MatchRow.revision,
                            MatchRow.position_version,
                            MatchRow.event_sequence,
                        )
                        .where(MatchRow.id.in_(ids))
                        .order_by(MatchRow.id)
                    )
                ).all()
            )

    async def bundle(self, run_id: str) -> bytes:
        queue = ExperimentQueue(self.store)
        run = await queue.snapshot(run_id)
        if run["state"] not in TERMINAL_RUNS or any(j["state"] not in SETTLED for j in run["jobs"]):
            raise ReportConflict("Finish or cancel the batch before exporting a stable report.")
        ids = [j["id"] for j in run["jobs"]]
        before = await self.markers(ids)
        async with self.store.sessions() as session:
            row = await session.get(ExperimentRow, run["experiment_id"])
            document = row.document
            manifest = {key: document[key] for key in HASH_FIELDS}
            if "tournament" in document:
                manifest["tournament"] = document["tournament"]
            if canonical_hash(manifest) != document["configuration_hash"]:
                raise ReportConflict("Saved experiment hash does not match its manifest.")
            manifest.update(
                configuration_hash=document["configuration_hash"],
                id=document["id"],
                created_at=document["created_at"],
                warnings=document.get("warnings", []),
            )
            opponents, _, _ = resolve_tournament(manifest, run["jobs"])
            schedule = {item["number"]: item for item in manifest["schedule"]}
            games = {}
            move_rows = []
            pg_ns = []
            for job in run["jobs"]:
                match = await session.get(MatchRow, job["id"])
                if match is None:
                    continue
                pair = opponents.get(job["number"])
                if pair is None:
                    raise ReportConflict("A saved match has unresolved tournament opponents.")
                game = chess.pgn.Game()
                try:
                    board = chess.Board(match.initial_fen)
                except ValueError:
                    raise ReportConflict(
                        "Saved match opening is invalid; export was not created."
                    ) from None
                if match.initial_fen != schedule[job["number"]]["initial_fen"]:
                    raise ReportConflict("Saved match opening does not match its experiment.")
                game.setup(board)
                game.headers.update(
                    Event="AI Chess Lounge Model Lab",
                    Site="AI Chess Lounge",
                    Date=match.created_at.strftime("%Y.%m.%d"),
                    Round=str(job["number"]),
                    White=safe_header(pair[0]),
                    Black=safe_header(pair[1]),
                    Result=job["result"]
                    if job["state"] == "completed" and job["result"] in CHESS_RESULTS
                    else "*",
                    ExperimentHash=manifest["configuration_hash"],
                    RunId=run_id,
                    MatchId=job["id"],
                    JobState=job["state"],
                    JobResult=job["result"] or "unplayed",
                )
                node = game
                count = 0
                moves = await session.stream_scalars(
                    select(MoveRow)
                    .where(MoveRow.match_id == match.id, MoveRow.generation == match.generation)
                    .order_by(MoveRow.ply)
                    .execution_options(yield_per=100)
                )
                async for move in moves:
                    if len(move_rows) >= MAX_EXPORT_MOVES:
                        raise ReportTooLarge(
                            "Export exceeds 25,000 accepted moves. Use a smaller experiment."
                        )
                    try:
                        parsed = chess.Move.from_uci(move.uci)
                    except ValueError:
                        raise ReportConflict(
                            "Saved move is invalid; export was not created."
                        ) from None
                    if move.ply != count + 1 or parsed not in board.legal_moves:
                        raise ReportConflict(
                            "Saved move sequence is inconsistent; export was not created."
                        )
                    board.push(parsed)
                    if board.fen() != move.fen:
                        raise ReportConflict(
                            "Saved move position is inconsistent; export was not created."
                        )
                    node = node.add_variation(parsed)
                    count += 1
                    move_rows.append(
                        dict(
                            match_id=match.id,
                            game_number=job["number"],
                            ply=move.ply,
                            uci=move.uci,
                            san=move.san,
                            fen=move.fen,
                            elapsed_ms=move.elapsed_ms,
                            white_remaining_ms=move.white_remaining_ms,
                            black_remaining_ms=move.black_remaining_ms,
                        )
                    )
                if count != match.position_version or board.fen() != match.current_fen:
                    raise ReportConflict(
                        "Saved match changed or is inconsistent; retry the export."
                    )
                games[match.id] = {
                    "generation": match.generation,
                    "revision": match.revision,
                    "plies": count,
                }
                pg_ns.append(str(game))

        metrics = await ExperimentMetrics(self.store).get(run_id)
        if before != await self.markers(ids) or run != await queue.snapshot(run_id):
            raise ReportConflict("Batch changed while exporting. Retry after it has settled.")
        if metrics["source_revision"] != run["revision"]:
            raise ReportConflict("Batch changed while reporting. Retry after it has settled.")
        report = {
            "schema_version": "1.0",
            "configuration_hash": manifest["configuration_hash"],
            "run": run,
            "match_versions": games,
            "metrics": metrics,
            "scope": (
                "Stable terminal run. Only recorded matches have PGN; no-results use *. "
                "Private move text and raw events are excluded."
            ),
        }
        competitors = []
        for competitor in metrics["competitors"]:
            competitors.append(
                {
                    **{
                        k: competitor[k]
                        for k in ("key", "provider", "model", "effort", "division", "pool")
                    },
                    **competitor["games"],
                    **competitor["reliability"],
                    "score_rate": competitor["strength"]["score_rate"],
                    "accepted_moves": competitor["efficiency"]["accepted_moves"],
                    "latency_p50_ms": competitor["efficiency"]["latency_ms"]["p50"],
                    "latency_p95_ms": competitor["efficiency"]["latency_ms"]["p95"],
                    "reported_cost_usd": competitor["efficiency"]["usage"]["estimated_cost_usd"][
                        "total"
                    ],
                    "cost_observed_moves": competitor["efficiency"]["usage"]["estimated_cost_usd"][
                        "observed_moves"
                    ],
                    "cost_missing_moves": competitor["efficiency"]["usage"]["estimated_cost_usd"][
                        "missing_moves"
                    ],
                }
            )
        files = {
            "manifest.json": json_bytes(manifest),
            "report.json": json_bytes(report),
            "competitors.csv": csv_bytes(list(competitors[0]), competitors),
            "games.csv": csv_bytes(["id", "number", "state", "result", "has_game"], run["jobs"]),
            "moves.csv": csv_bytes(
                [
                    "match_id",
                    "game_number",
                    "ply",
                    "uci",
                    "san",
                    "fen",
                    "elapsed_ms",
                    "white_remaining_ms",
                    "black_remaining_ms",
                ],
                move_rows,
            ),
            "games.pgn": ("\n\n".join(pg_ns) + ("\n" if pg_ns else "")).encode(),
            "README.txt": (
                b"AI Chess Lounge report bundle v1\n"
                b"manifest.json preserves the hash and public configuration, including labels.\n"
                b"report.json records methods, assumptions, coverage and run/match revisions.\n"
                b"CSV is UTF-8; blank numeric cells mean unknown, not zero.\n"
                b"Formula-like CSV text is apostrophe-prefixed; JSON retains original values.\n"
                b"games.pgn uses each initial FEN; no-results use Result *.\n"
                b"Unplayed/blocked jobs have no fabricated PGN.\n"
                b"Private move plans/threats/reasoning and raw events are excluded.\n"
                b"Usage covers accepted moves only; costs are reported estimates, not bills.\n"
                b"Hashes verify content, not signatures, determinism or calibrated strength.\n"
            ),
        }
        files["checksums.json"] = json_bytes(
            {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}
        )
        if sum(map(len, files.values())) > MAX_EXPORT_BYTES:
            raise ReportTooLarge("Export exceeds 16 MiB. Use a smaller experiment.")

        def compress():
            output = io.BytesIO()
            with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
                for name, content in files.items():
                    info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                    info.compress_type = ZIP_DEFLATED
                    archive.writestr(info, content)
            return output.getvalue()

        return await asyncio.to_thread(compress)
