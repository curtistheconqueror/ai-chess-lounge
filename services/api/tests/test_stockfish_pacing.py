import asyncio
from time import monotonic

import chess
import pytest
from lounge_api.adapters import AdapterConfigurationError, StockfishPlayerAdapter
from lounge_api.player_protocol import AssistanceDivision, MoveRequest, PlayerConfiguration


class InstantEngine:
    available = True

    async def choose_move(self, board, **_):
        return type("Result", (), {"uci": next(iter(board.legal_moves)).uci()})()


def request(deadline_ms: int = 20_000) -> MoveRequest:
    board = chess.Board()
    return MoveRequest(
        match_id="pacing",
        position_version=0,
        fen=board.fen(),
        color="white",
        moves_uci=[],
        pgn="",
        legal_moves=[move.uci() for move in board.legal_moves],
        remaining_ms=300_000,
        move_deadline_ms=deadline_ms,
        division=list(AssistanceDivision)[0],
    )


def player(**settings) -> PlayerConfiguration:
    return PlayerConfiguration.stockfish("white").model_copy(
        update={"settings": {"color": "white", "target_elo": 1600, **settings}}
    )


def timed(pacing: int | None, deadline_ms: int = 20_000) -> float:
    adapter = StockfishPlayerAdapter(InstantEngine())
    settings = {} if pacing is None else {"reply_pacing_ms": pacing}

    async def run():
        started = monotonic()
        proposal = await adapter.choose_move(request(deadline_ms), player(**settings))
        assert proposal.move in request().legal_moves
        return monotonic() - started

    return asyncio.run(run())


def test_reply_pacing_holds_the_reply_for_the_configured_time():
    assert timed(None) < 0.2
    assert timed(0) < 0.2
    assert 0.55 <= timed(600) < 1.2


def test_reply_pacing_never_approaches_the_move_deadline():
    # A 400ms deadline leaves at most 150ms of pacing (250ms safety margin).
    assert timed(5_000, deadline_ms=400) < 0.35


@pytest.mark.parametrize("value", [-1, 5_001, 1.5, True, "1000"])
def test_reply_pacing_rejects_invalid_values(value):
    with pytest.raises((ValueError, AdapterConfigurationError)):
        StockfishPlayerAdapter(InstantEngine()).validate_configuration(
            player(reply_pacing_ms=value)
        )
