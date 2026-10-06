"""Participant SDK for Pipeline.

Participants write `def solve(game): ...` using the Game interface provided here.
Only read-only geometry, current chain end, remaining piece ids, would_collide helper,
and the place() action are accessible.
"""

from __future__ import annotations
from typing import Any, Callable, Dict, List, Optional, Tuple


class Game:
    """Participant interface for Pipeline.

    Properties:
    - source: Tuple[int, int]
    - sink: Tuple[int, int]
    - obstacles: List of obstacle geometry dictionaries
    - pieces: List of piece dictionaries (id, kind, shape, start, end/arms)
    - chain_end: Tuple[int, int] (current end of the chain)

    Methods:
    - remaining() -> List[int]: IDs of unplaced pieces
    - would_collide(piece_id: int, arm: Optional[int] = None) -> bool: Free collision check
    - place(piece_id: int, arm: Optional[int] = None) -> Dict[str, Any]: Places piece, costs 1 step
    """

    def __init__(
        self,
        snapshot: Dict[str, Any],
        place_fn: Optional[Callable[[int, Optional[int]], Dict[str, Any]]] = None,
        would_collide_fn: Optional[Callable[[int, Optional[int]], bool]] = None,
    ) -> None:
        self.source: Tuple[int, int] = tuple(snapshot["source"])  # type: ignore
        self.sink: Tuple[int, int] = tuple(snapshot["sink"])  # type: ignore
        self.grid_size: Tuple[int, int] = tuple(snapshot.get("grid_size", (200, 200)))  # type: ignore
        self.pipe_radius: int = snapshot.get("pipe_radius", 2)
        self.joint_exempt_radius: int = snapshot.get("joint_exempt_radius", 3)

        self.obstacles: List[Dict[str, Any]] = list(snapshot.get("obstacles", []))
        self.pieces: List[Dict[str, Any]] = list(snapshot.get("pieces", []))

        self._chain_end: Tuple[int, int] = tuple(snapshot.get("chain_end", self.source))  # type: ignore
        self._remaining_ids: List[int] = list(snapshot.get("remaining", [p["id"] for p in self.pieces]))

        self._place_fn = place_fn
        self._would_collide_fn = would_collide_fn

    @property
    def chain_end(self) -> Tuple[int, int]:
        return self._chain_end

    def remaining(self) -> List[int]:
        return list(self._remaining_ids)

    def would_collide(self, piece_id: int, arm: Optional[int] = None) -> bool:
        """Collision-check helper. Free in steps (costs only CPU)."""
        if self._would_collide_fn is not None:
            return self._would_collide_fn(piece_id, arm)
        return True

    def place(self, piece_id: int, arm: Optional[int] = None) -> Dict[str, Any]:
        """Attempt to place a piece at the current chain end.

        Every call advances step count and game time by 1 unit.
        Returns:
            {"legal": bool, "chain_end": (x, y), "solved": bool}
        """
        if self._place_fn is None:
            raise RuntimeError("place() called on detached Game instance.")

        res = self._place_fn(piece_id, arm)
        if res.get("legal"):
            self._chain_end = tuple(res["chain_end"])  # type: ignore
            if piece_id in self._remaining_ids:
                self._remaining_ids.remove(piece_id)

        return {
            "legal": bool(res.get("legal", False)),
            "chain_end": self._chain_end,
            "solved": bool(res.get("solved", False)),
        }
