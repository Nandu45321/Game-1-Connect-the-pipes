"""Game engine managing state, step accounting, placement validation, and replay logging."""

from __future__ import annotations
from typing import Any, Dict, List, Optional, Set, Tuple
from pipeline.engine.model import (
    Piece,
    Junction,
    Obstacle,
    Puzzle,
    ChainState,
    DEFAULT_UNIT_TIME,
)
from pipeline.engine.collision import would_collide


class GameEngine:
    """Headless, deterministic engine for a single puzzle run."""

    def __init__(self, puzzle: Puzzle, unit_time: float = DEFAULT_UNIT_TIME) -> None:
        self.puzzle = puzzle
        self.source: Tuple[int, int] = puzzle.source
        self.sink: Tuple[int, int] = puzzle.sink
        self.grid_size: Tuple[int, int] = puzzle.grid_size
        self.pipe_radius: int = puzzle.pipe_radius
        self.joint_exempt_radius: int = puzzle.joint_exempt_radius
        self.unit_time: float = unit_time

        self.pieces: Dict[int, Piece | Junction] = dict(puzzle.pieces)
        self.obstacles: List[Obstacle] = list(puzzle.obstacles)
        self._obstacle_cells: Set[Tuple[int, int]] = puzzle.all_obstacle_cells()

        # Dynamic state
        self.chain_end: Tuple[int, int] = self.source
        self.placed_piece_ids: Set[int] = set()
        self.placed_cells: Set[Tuple[int, int]] = set()
        self.last_piece_cells: Set[Tuple[int, int]] = set()
        self.history: List[Dict[str, Any]] = []

        # Step accounting
        self.steps_total: int = 0
        self.steps_legal: int = 0
        self.steps_illegal: int = 0
        self.is_solved: bool = False

        # Replay event log
        self.replay_events: List[Dict[str, Any]] = []

    @property
    def game_time(self) -> float:
        """Deterministic game time based solely on steps."""
        return self.steps_total * self.unit_time

    def remaining(self) -> List[int]:
        """Return IDs of unplaced pieces."""
        return [pid for pid in self.pieces if pid not in self.placed_piece_ids]

    def would_collide(self, piece_id: int, arm: Optional[int] = None) -> bool:
        """Check if placing piece_id at the current chain end would collide.

        Read-only helper: costs 0 steps.
        Returns True if placement collides, piece does not exist, piece is already
        placed, or arm is invalid. Returns False otherwise.
        """
        if piece_id not in self.pieces:
            return True
        if piece_id in self.placed_piece_ids:
            return True

        piece = self.pieces[piece_id]
        if isinstance(piece, Junction):
            if arm is None or arm < 0 or arm >= len(piece.arms):
                return True

        return would_collide(
            piece=piece,
            position=self.chain_end,
            placed_cells=self.placed_cells,
            obstacle_cells=self._obstacle_cells,
            joint_exempt_radius=self.joint_exempt_radius,
            shared_joint=self.chain_end,
            arm=arm,
            exempt_cells=self.last_piece_cells,
        )

    def place(self, piece_id: int, arm: Optional[int] = None) -> Dict[str, Any]:
        """Attempt to place a piece at the current chain end.

        Every call advances step counts and game time by 1 unit.
        Returns:
            {"legal": bool, "chain_end": (x, y), "solved": bool}
        """
        self.steps_total += 1
        pos = self.chain_end

        # Validate piece existence
        if piece_id not in self.pieces:
            self.steps_illegal += 1
            self._log_event(piece_id, arm, legal=False, reason="unknown_piece")
            return {"legal": False, "chain_end": self.chain_end, "solved": self.is_solved}

        # Validate unplaced
        if piece_id in self.placed_piece_ids:
            self.steps_illegal += 1
            self._log_event(piece_id, arm, legal=False, reason="already_placed")
            return {"legal": False, "chain_end": self.chain_end, "solved": self.is_solved}

        piece = self.pieces[piece_id]

        # Validate junction arm
        if isinstance(piece, Junction):
            if arm is None or arm < 0 or arm >= len(piece.arms):
                self.steps_illegal += 1
                self._log_event(piece_id, arm, legal=False, reason="invalid_arm")
                return {"legal": False, "chain_end": self.chain_end, "solved": self.is_solved}

        # Collision check
        collides = would_collide(
            piece=piece,
            position=pos,
            placed_cells=self.placed_cells,
            obstacle_cells=self._obstacle_cells,
            joint_exempt_radius=self.joint_exempt_radius,
            shared_joint=pos,
            arm=arm,
            exempt_cells=self.last_piece_cells,
        )

        if collides:
            self.steps_illegal += 1
            self._log_event(piece_id, arm, legal=False, reason="collision")
            return {"legal": False, "chain_end": self.chain_end, "solved": self.is_solved}

        # Legal placement!
        self.steps_legal += 1

        # Calculate new chain end
        if isinstance(piece, Junction):
            assert arm is not None
            chosen_arm = piece.arms[arm]
            new_chain_end = (pos[0] + chosen_arm.end[0], pos[1] + chosen_arm.end[1])
        else:
            new_chain_end = (pos[0] + piece.end[0], pos[1] + piece.end[1])

        # Occupy world cells
        occupied: Set[Tuple[int, int]] = set()
        for lx, ly in piece.local_cells:
            wx = pos[0] + lx
            wy = pos[1] + ly
            occupied.add((wx, wy))
            self.placed_cells.add((wx, wy))

        self.last_piece_cells = occupied
        self.placed_piece_ids.add(piece_id)
        self.chain_end = new_chain_end

        if self.chain_end == self.sink:
            self.is_solved = True

        placement_record = {
            "piece_id": piece_id,
            "position": pos,
            "chosen_arm": arm,
            "new_chain_end": new_chain_end,
        }
        self.history.append(placement_record)
        self._log_event(piece_id, arm, legal=True, new_chain_end=new_chain_end)

        return {"legal": True, "chain_end": self.chain_end, "solved": self.is_solved}

    def _log_event(
        self,
        piece_id: int,
        arm: Optional[int],
        legal: bool,
        reason: Optional[str] = None,
        new_chain_end: Optional[Tuple[int, int]] = None,
    ) -> None:
        self.replay_events.append(
            {
                "step": self.steps_total,
                "game_time": self.game_time,
                "piece_id": piece_id,
                "arm": arm,
                "legal": legal,
                "reason": reason,
                "chain_end": list(new_chain_end if new_chain_end else self.chain_end),
                "solved": self.is_solved,
            }
        )

    def get_replay_log(self) -> Dict[str, Any]:
        """Return complete replay data structure."""
        return {
            "puzzle": self.puzzle.to_dict(),
            "summary": {
                "solved": self.is_solved,
                "steps_total": self.steps_total,
                "steps_legal": self.steps_legal,
                "steps_illegal": self.steps_illegal,
                "game_time": self.game_time,
            },
            "history": self.history,
            "events": self.replay_events,
        }

    def get_api_snapshot(self) -> Dict[str, Any]:
        """Strictly geometry-only read-only snapshot for the participant SDK."""
        return {
            "source": self.source,
            "sink": self.sink,
            "grid_size": self.grid_size,
            "pipe_radius": self.pipe_radius,
            "joint_exempt_radius": self.joint_exempt_radius,
            "obstacles": [o.to_api_dict() for o in self.obstacles],
            "pieces": [p.to_api_dict() for p in self.pieces.values()],
            "chain_end": self.chain_end,
            "remaining": self.remaining(),
        }

    def clone(self) -> GameEngine:
        """Create a deep copy of engine state (for reference solvers / search)."""
        engine = GameEngine(self.puzzle, unit_time=self.unit_time)
        engine.chain_end = self.chain_end
        engine.placed_piece_ids = set(self.placed_piece_ids)
        engine.placed_cells = set(self.placed_cells)
        engine.last_piece_cells = set(self.last_piece_cells)
        engine.history = [dict(h) for h in self.history]
        engine.steps_total = self.steps_total
        engine.steps_legal = self.steps_legal
        engine.steps_illegal = self.steps_illegal
        engine.is_solved = self.is_solved
        engine.replay_events = [dict(e) for e in self.replay_events]
        return engine
