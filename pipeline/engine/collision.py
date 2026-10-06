"""Collision detection and rasterization for Pipeline.

Single source of truth for collision checks across the game engine, reference
solvers, and participant helper API.
"""

from __future__ import annotations
import math
from typing import Any, Dict, List, Optional, Set, Tuple
from pipeline.engine.model import (
    Piece,
    Junction,
    DEFAULT_GRID_SIZE,
    DEFAULT_PIPE_RADIUS,
    DEFAULT_JOINT_EXEMPT_RADIUS,
)


def rasterize_points_thickened(
    sampled_points: List[Tuple[float, float]],
    radius: int,
) -> Set[Tuple[int, int]]:
    """Rasterize sampled curve points thickened by a given radius into integer cells."""
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

    return cells


def would_collide(
    piece: Piece | Junction,
    position: Tuple[int, int],
    placed_cells: Set[Tuple[int, int]],
    obstacle_cells: Set[Tuple[int, int]],
    joint_exempt_radius: int = DEFAULT_JOINT_EXEMPT_RADIUS,
    shared_joint: Optional[Tuple[int, int]] = None,
    arm: Optional[int] = None,
    exempt_cells: Optional[Set[Tuple[int, int]]] = None,
) -> bool:
    """Check if placing a piece at `position` would collide.

    Parameters:
    - piece: Piece or Junction to test.
    - position: (x, y) where piece start (0, 0) is placed.
    - placed_cells: set of cells already occupied by previously placed pipes.
    - obstacle_cells: set of obstacle cells.
    - joint_exempt_radius: radius around shared_joint where overlap with
      previous pipes is exempted.
    - shared_joint: position of the connecting joint (defaults to `position`).
    - arm: optional designated continuing arm for Junction (all arms occupy space).
    - exempt_cells: specific cells (from the connecting pipe) that are allowed to overlap near the joint.

    Returns:
    - True if placement collides with obstacles or previously placed pipes
      (outside the exempt joint area), False otherwise.
    """
    pos_x, pos_y = position

    # Joint exemption center
    if shared_joint is None:
        joint_x, joint_y = pos_x, pos_y
    else:
        joint_x, joint_y = shared_joint
    exempt_sq = joint_exempt_radius * joint_exempt_radius

    # Use set comprehension for fast C-level translation
    shifted_local = {(lx + pos_x, ly + pos_y) for lx, ly in piece.local_cells}

    # 1. Obstacle collision (NEVER exempt)
    if shifted_local & obstacle_cells:
        return True

    # 2. Previously placed pipe collision
    collisions = shifted_local & placed_cells
    if collisions:
        if not exempt_cells:
            return True
        for cx, cy in collisions:
            if (cx, cy) not in exempt_cells:
                return True
            # Check if within joint exemption circle
            j_dx = cx - joint_x
            j_dy = cy - joint_y
            if j_dx * j_dx + j_dy * j_dy > exempt_sq:
                return True

    return False
