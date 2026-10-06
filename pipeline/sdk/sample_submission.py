"""Sample participant submission for Pipeline.

Two-phase solver:
  1. Greedy: always pick the move bringing chain_end closest to sink.
  2. If greedy gets stuck, try any legal move (without caring about distance).

This is a demonstration only. Participants should write smarter solvers.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Tuple
from pipeline.sdk.pipeline_api import Game


def solve(game: Game) -> None:
    sink = game.sink
    piece_map: Dict[int, Dict[str, Any]] = {p["id"]: p for p in game.pieces}

    def get_options(piece: Dict[str, Any]) -> List[Tuple[Optional[int], Tuple[int, int]]]:
        if piece.get("kind") == "junction":
            return [(arm["arm_id"], tuple(arm["end"])) for arm in piece.get("arms", [])]  # type: ignore
        return [(None, tuple(piece["end"]))]  # type: ignore

    def all_legal_moves() -> List[Tuple[float, int, Optional[int]]]:
        """Return all legal (distance_to_sink, pid, arm) sorted by distance."""
        moves: List[Tuple[float, int, Optional[int]]] = []
        pos = game.chain_end
        for pid in game.remaining():
            piece = piece_map[pid]
            for arm, disp in get_options(piece):
                if not game.would_collide(pid, arm=arm):
                    next_pos = (pos[0] + disp[0], pos[1] + disp[1])
                    d = math.hypot(sink[0] - next_pos[0], sink[1] - next_pos[1])
                    moves.append((d, pid, arm))
        moves.sort()
        return moves

    while game.remaining():
        if game.chain_end == sink:
            return

        moves = all_legal_moves()
        if not moves:
            break  # truly stuck

        # Pick move that gets closest to sink
        _, pid, arm = moves[0]
        res = game.place(pid, arm=arm)
        if res.get("solved"):
            return
