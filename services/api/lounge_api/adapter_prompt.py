from __future__ import annotations

from .player_protocol import MoveRequest

SYSTEM_INSTRUCTION = (
    "You are a chess competitor in AI Chess Lounge. Return one UCI move and "
    "brief public-facing summaries using the required structured format."
)


def human_suggestion_prompt(request: MoveRequest) -> list[str]:
    if not request._human_suggestion:
        return []
    return [
        f"Human suggestion (UCI): {request._human_suggestion}. "
        "Consider this optional suggestion; you retain final move authority and may "
        "choose any legal move. This is Human-AI Team exhibition assistance."
    ]


def move_prompt(request: MoveRequest) -> str:
    lines = [
        f"You are playing {request.color}.",
        f"FEN: {request.fen}",
        f"Moves (UCI): {' '.join(request.moves_uci) or '(none)'}",
        f"PGN: {request.pgn}",
        f"Assistance division: {request.division.value}",
    ]
    if request.legal_moves is not None:
        lines.append(f"Legal moves (UCI): {' '.join(request.legal_moves)}")
    lines.extend(human_suggestion_prompt(request))
    lines.append(
        "Choose exactly one legal move. Provide only a concise public plan and threat; "
        "never reveal private chain-of-thought."
    )
    return "\n".join(lines)
