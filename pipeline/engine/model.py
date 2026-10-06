"""Data models for Pipeline: Pieces, Junctions, Obstacles, Puzzles, and ChainState."""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

DEFAULT_GRID_SIZE: Tuple[int, int] = (200, 200)
DEFAULT_PIPE_RADIUS: int = 2
DEFAULT_JOINT_EXEMPT_RADIUS: int = 3
DEFAULT_UNIT_TIME: float = 1.0


def sample_curve(
    curve_type: str,
    start: Tuple[int, int],
    end: Tuple[int, int],
    control_points: Optional[List[Tuple[float, float]]] = None,
    samples_per_unit: float = 2.0,
    min_samples: int = 25,
) -> List[Tuple[float, float]]:
    """Deterministically sample points along a 2D parametric curve p(t), t in [0, 1].

    Guarantees p(0) == start and p(1) == end.
    """
    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    chord_len = math.hypot(ex - sx, ey - sy)
    num_samples = max(min_samples, int(math.ceil(chord_len * samples_per_unit)))

    points: List[Tuple[float, float]] = []

    if curve_type == "line" or not control_points:
        for i in range(num_samples + 1):
            t = i / float(num_samples)
            x = (1.0 - t) * sx + t * ex
            y = (1.0 - t) * sy + t * ey
            points.append((round(x, 4), round(y, 4)))
    elif curve_type == "bezier_quad":
        c0 = control_points[0]
        cx, cy = float(c0[0]), float(c0[1])
        for i in range(num_samples + 1):
            t = i / float(num_samples)
            omt = 1.0 - t
            x = omt * omt * sx + 2.0 * omt * t * cx + t * t * ex
            y = omt * omt * sy + 2.0 * omt * t * cy + t * t * ey
            points.append((round(x, 4), round(y, 4)))
    elif curve_type == "bezier_cubic":
        c0, c1 = control_points[0], control_points[1]
        c0x, c0y = float(c0[0]), float(c0[1])
        c1x, c1y = float(c1[0]), float(c1[1])
        for i in range(num_samples + 1):
            t = i / float(num_samples)
            omt = 1.0 - t
            x = (
                omt**3 * sx
                + 3.0 * omt * omt * t * c0x
                + 3.0 * omt * t * t * c1x
                + t**3 * ex
            )
            y = (
                omt**3 * sy
                + 3.0 * omt * omt * t * c0y
                + 3.0 * omt * t * t * c1y
                + t**3 * ey
            )
            points.append((round(x, 4), round(y, 4)))
    elif curve_type == "sine":
        # Sine wave superimposed on chord
        dx = ex - sx
        dy = ey - sy
        normal_x = -dy / (chord_len if chord_len > 0 else 1.0)
        normal_y = dx / (chord_len if chord_len > 0 else 1.0)
        amp = control_points[0][0] if control_points else 5.0
        freq = control_points[0][1] if control_points and len(control_points[0]) > 1 else 1.0

        for i in range(num_samples + 1):
            t = i / float(num_samples)
            base_x = (1.0 - t) * sx + t * ex
            base_y = (1.0 - t) * sy + t * ey
            offset = amp * math.sin(freq * math.pi * t)
            x = base_x + offset * normal_x
            y = base_y + offset * normal_y
            points.append((round(x, 4), round(y, 4)))
    elif curve_type == "polyline":
        pts_list = [(sx, sy)] + [(float(p[0]), float(p[1])) for p in (control_points or [])] + [(ex, ey)]
        seg_lengths = [math.hypot(pts_list[j+1][0]-pts_list[j][0], pts_list[j+1][1]-pts_list[j][1]) for j in range(len(pts_list)-1)]
        total_len = sum(seg_lengths)
        for i in range(num_samples + 1):
            target = (i / float(num_samples)) * total_len
            curr = 0.0
            for j in range(len(pts_list)-1):
                if curr + seg_lengths[j] >= target - 1e-6 or j == len(pts_list)-2:
                    t_val = (target - curr) / (seg_lengths[j] if seg_lengths[j] > 0 else 1.0)
                    x = (1 - t_val) * pts_list[j][0] + t_val * pts_list[j+1][0]
                    y = (1 - t_val) * pts_list[j][1] + t_val * pts_list[j+1][1]
                    points.append((round(x, 4), round(y, 4)))
                    break
                curr += seg_lengths[j]
    else:
        # Fallback to straight line
        for i in range(num_samples + 1):
            t = i / float(num_samples)
            x = (1.0 - t) * sx + t * ex
            y = (1.0 - t) * sy + t * ey
            points.append((round(x, 4), round(y, 4)))

    # Ensure start and end are exactly as specified
    points[0] = (float(start[0]), float(start[1]))
    points[-1] = (float(end[0]), float(end[1]))
    return points


def compute_thickened_cells(
    sampled_points: List[Tuple[float, float]],
    radius: int,
) -> frozenset[Tuple[int, int]]:
    """Compute integer grid cells covered by sweeping a circle of given radius along sampled points."""
    r_sq = radius * radius
    cells: Set[Tuple[int, int]] = set()

    for px, py in sampled_points:
        min_x = int(math.floor(px - radius))
        max_x = int(math.ceil(px + radius))
        min_y = int(math.floor(py - radius))
        max_y = int(math.ceil(py + radius))

        for cx in range(min_x, max_x + 1):
            for cy in range(min_y, max_y + 1):
                dx = cx - px
                dy = cy - py
                if dx * dx + dy * dy <= r_sq + 1e-6:
                    cells.add((cx, cy))

    return frozenset(cells)


@dataclass(frozen=True)
class Piece:
    """A standard pipe piece with start at (0, 0) and an integer end vector."""

    id: int
    end: Tuple[int, int]
    curve_type: str = "line"
    control_points: Optional[Tuple[Tuple[float, float], ...]] = None
    sampled_points: Tuple[Tuple[float, float], ...] = field(default_factory=tuple)
    local_cells: frozenset[Tuple[int, int]] = field(default_factory=frozenset)
    kind: str = "pipe"
    start: Tuple[int, int] = (0, 0)

    @classmethod
    def create(
        cls,
        id: int,
        end: Tuple[int, int],
        curve_type: str = "line",
        control_points: Optional[List[Tuple[float, float]]] = None,
        pipe_radius: int = DEFAULT_PIPE_RADIUS,
    ) -> Piece:
        pts = sample_curve(
            curve_type,
            (0, 0),
            end,
            control_points=control_points,
        )
        ctrl_tuple = tuple(control_points) if control_points else None
        cells = compute_thickened_cells(pts, pipe_radius)
        return cls(
            id=id,
            end=end,
            curve_type=curve_type,
            control_points=ctrl_tuple,
            sampled_points=tuple(pts),
            local_cells=cells,
            kind="pipe",
            start=(0, 0),
        )

    def to_api_dict(self) -> Dict[str, Any]:
        """Expose clean read-only snapshot for the participant SDK (no secret flags)."""
        return {
            "id": self.id,
            "kind": self.kind,
            "start": self.start,
            "end": self.end,
            "shape": {
                "curve_type": self.curve_type,
                "control_points": list(self.control_points) if self.control_points else [],
                "sampled_points": list(self.sampled_points),
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialization for replay / engine storage."""
        return {
            "id": self.id,
            "kind": self.kind,
            "start": list(self.start),
            "end": list(self.end),
            "curve_type": self.curve_type,
            "control_points": [list(cp) for cp in self.control_points] if self.control_points else [],
            "sampled_points": [list(p) for p in self.sampled_points],
            "local_cells": [list(c) for c in sorted(self.local_cells)],
        }


@dataclass(frozen=True)
class Arm:
    """An arm of a junction piece."""

    arm_id: int
    end: Tuple[int, int]
    curve_type: str
    control_points: Optional[Tuple[Tuple[float, float], ...]]
    sampled_points: Tuple[Tuple[float, float], ...]
    local_cells: frozenset[Tuple[int, int]]

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "end": self.end,
            "shape": {
                "curve_type": self.curve_type,
                "control_points": list(self.control_points) if self.control_points else [],
                "sampled_points": list(self.sampled_points),
            },
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "arm_id": self.arm_id,
            "end": list(self.end),
            "curve_type": self.curve_type,
            "control_points": [list(cp) for cp in self.control_points] if self.control_points else [],
            "sampled_points": [list(p) for p in self.sampled_points],
            "local_cells": [list(c) for c in sorted(self.local_cells)],
        }


@dataclass(frozen=True)
class Junction:
    """A junction piece with input at (0, 0) and 2 or 3 output arms."""

    id: int
    arms: Tuple[Arm, ...]
    local_cells: frozenset[Tuple[int, int]]
    kind: str = "junction"
    start: Tuple[int, int] = (0, 0)

    @classmethod
    def create(
        cls,
        id: int,
        arm_configs: List[Dict[str, Any]],
        pipe_radius: int = DEFAULT_PIPE_RADIUS,
    ) -> Junction:
        built_arms: List[Arm] = []
        all_cells: Set[Tuple[int, int]] = set()

        for idx, cfg in enumerate(arm_configs):
            end = tuple(cfg["end"])
            curve_type = cfg.get("curve_type", "line")
            ctrl = cfg.get("control_points")
            ctrl_tuple = tuple(ctrl) if ctrl else None
            pts = sample_curve(curve_type, (0, 0), end, control_points=ctrl)
            arm_cells = compute_thickened_cells(pts, pipe_radius)
            all_cells.update(arm_cells)

            built_arms.append(
                Arm(
                    arm_id=idx,
                    end=end,
                    curve_type=curve_type,
                    control_points=ctrl_tuple,
                    sampled_points=tuple(pts),
                    local_cells=arm_cells,
                )
            )

        return cls(
            id=id,
            arms=tuple(built_arms),
            local_cells=frozenset(all_cells),
            kind="junction",
            start=(0, 0),
        )

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "start": self.start,
            "arms": [arm.to_api_dict() for arm in self.arms],
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "start": list(self.start),
            "arms": [arm.to_dict() for arm in self.arms],
            "local_cells": [list(c) for c in sorted(self.local_cells)],
        }


@dataclass(frozen=True)
class Obstacle:
    """A static obstacle that pipes may not overlap."""

    id: int
    cells: frozenset[Tuple[int, int]]
    polygon: Optional[Tuple[Tuple[int, int], ...]] = None

    @classmethod
    def from_rect(cls, id: int, x: int, y: int, width: int, height: int) -> Obstacle:
        cells = set()
        for cx in range(x, x + width):
            for cy in range(y, y + height):
                cells.add((cx, cy))
        poly = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
        return cls(id=id, cells=frozenset(cells), polygon=poly)

    @classmethod
    def from_cells(cls, id: int, cells: Set[Tuple[int, int]]) -> Obstacle:
        return cls(id=id, cells=frozenset(cells))

    def to_api_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cells": [list(c) for c in sorted(self.cells)],
            "polygon": [list(p) for p in self.polygon] if self.polygon else None,
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "cells": [list(c) for c in sorted(self.cells)],
            "polygon": [list(p) for p in self.polygon] if self.polygon else None,
        }


@dataclass
class ChainState:
    """Current state of placed pipes on the board."""

    current_chain_end: Tuple[int, int]
    placed_piece_ids: List[int] = field(default_factory=list)
    placed_cells: Set[Tuple[int, int]] = field(default_factory=set)
    # List of records: {"piece_id": id, "position": (x, y), "chosen_arm": arm_id, "end": (x, y)}
    history: List[Dict[str, Any]] = field(default_factory=list)

    def clone(self) -> ChainState:
        return ChainState(
            current_chain_end=self.current_chain_end,
            placed_piece_ids=list(self.placed_piece_ids),
            placed_cells=set(self.placed_cells),
            history=[dict(h) for h in self.history],
        )


@dataclass
class Puzzle:
    """Full puzzle configuration."""

    source: Tuple[int, int]
    sink: Tuple[int, int]
    pieces: Dict[int, Piece | Junction]
    obstacles: List[Obstacle]
    grid_size: Tuple[int, int] = DEFAULT_GRID_SIZE
    pipe_radius: int = DEFAULT_PIPE_RADIUS
    joint_exempt_radius: int = DEFAULT_JOINT_EXEMPT_RADIUS
    seed: Optional[int] = None
    solution_path: Optional[List[Dict[str, Any]]] = None

    def all_obstacle_cells(self) -> Set[Tuple[int, int]]:
        cells: Set[Tuple[int, int]] = set()
        for obs in self.obstacles:
            cells.update(obs.cells)
        return cells

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": list(self.source),
            "sink": list(self.sink),
            "grid_size": list(self.grid_size),
            "pipe_radius": self.pipe_radius,
            "joint_exempt_radius": self.joint_exempt_radius,
            "seed": self.seed,
            "pieces": [p.to_dict() for p in self.pieces.values()],
            "obstacles": [o.to_dict() for o in self.obstacles],
        }

    def to_api_dict(self) -> Dict[str, Any]:
        """Strictly geometry-only read-only dictionary for the participant SDK."""
        return {
            "source": self.source,
            "sink": self.sink,
            "grid_size": self.grid_size,
            "pipe_radius": self.pipe_radius,
            "joint_exempt_radius": self.joint_exempt_radius,
            "pieces": [p.to_api_dict() for p in self.pieces.values()],
            "obstacles": [o.to_api_dict() for o in self.obstacles],
        }
