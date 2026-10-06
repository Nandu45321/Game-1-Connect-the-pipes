"""Unit tests for collision logic and joint exemption."""

import pytest
from pipeline.engine.model import Piece, Junction, Obstacle, DEFAULT_GRID_SIZE, DEFAULT_PIPE_RADIUS, DEFAULT_JOINT_EXEMPT_RADIUS
from pipeline.engine.collision import would_collide


def test_curves_touching_only_at_joint_are_legal():
    """Two pieces touching only at their shared connection joint must not collide."""
    # Piece 1: starts at (0, 0), ends at (10, 0)
    p1 = Piece.create(id=1, end=(10, 0), curve_type="line", pipe_radius=2)
    # Piece 2: starts at (0, 0), ends at (20, 0)
    p2 = Piece.create(id=2, end=(10, 0), curve_type="line", pipe_radius=2)

    # Place piece 1 at (50, 50)
    placed_cells = {(50 + lx, 50 + ly) for (lx, ly) in p1.local_cells}

    # Piece 2 connects at p1's end: (60, 50)
    # At (60, 50), p1's end and p2's start meet. Joint exemption should allow this!
    collides = would_collide(
        piece=p2,
        position=(60, 50),
        placed_cells=placed_cells,
        obstacle_cells=set(),
        shared_joint=(60, 50),
        exempt_cells=placed_cells,
    )
    assert not collides, "Two connected pipes at joint should NOT collide."


def test_crossing_curves_are_illegal():
    """Crossing curves that intersect outside the joint exemption must collide."""
    # Horizontal piece from (0, 0) to (20, 0)
    p_horiz = Piece.create(id=1, end=(20, 0), curve_type="line", pipe_radius=2)
    # Vertical piece from (0, 0) to (0, 20)
    p_vert = Piece.create(id=2, end=(0, 20), curve_type="line", pipe_radius=2)

    # Place horizontal pipe at (50, 50) -> spans from x=50 to x=70 at y=50
    placed_cells = {(50 + lx, 50 + ly) for (lx, ly) in p_horiz.local_cells}

    # Attempt to place vertical pipe at (60, 40) -> will cross at (60, 50)
    # Shared joint is at (60, 40), but the intersection is at (60, 50) (dist = 10 > 3)
    collides = would_collide(
        piece=p_vert,
        position=(60, 40),
        placed_cells=placed_cells,
        obstacle_cells=set(),
        shared_joint=(60, 40),
    )
    assert collides, "Crossing pipes outside joint exemption must collide."


def test_obstacle_collision_and_no_exemption():
    """A piece overlapping an obstacle is illegal, even near a joint."""
    p = Piece.create(id=1, end=(10, 0), curve_type="line", pipe_radius=2)

    # Obstacle placed along the pipe's path
    obs = Obstacle.from_rect(id=1, x=55, y=49, width=4, height=4)

    collides = would_collide(
        piece=p,
        position=(50, 50),
        placed_cells=set(),
        obstacle_cells=set(obs.cells),
        shared_joint=(50, 50),
    )
    assert collides, "Piece overlapping obstacle must collide."


def test_open_arms_of_junction_block_later_placements():
    """Unused open arms of a junction occupy space and block later placements."""
    # Junction with 2 arms: arm 0 heads east (15, 0), arm 1 heads south (0, 15)
    junc = Junction.create(
        id=1,
        arm_configs=[
            {"end": (15, 0), "curve_type": "line"},
            {"end": (0, 15), "curve_type": "line"},
        ],
        pipe_radius=2,
    )

    # Place junction at (50, 50)
    placed_cells = {(50 + lx, 50 + ly) for (lx, ly) in junc.local_cells}

    # Say arm 0 was chosen, so chain continued east to (65, 50).
    # Arm 1 sits pointing south from (50, 50) down to (50, 65).
    # Now suppose a subsequent pipe placed at (40, 58) heading east crosses (50, 58).
    crossing_pipe = Piece.create(id=2, end=(20, 0), curve_type="line", pipe_radius=2)

    collides = would_collide(
        piece=crossing_pipe,
        position=(40, 58),
        placed_cells=placed_cells,
        obstacle_cells=set(),
        shared_joint=(40, 58),
    )
    assert collides, "Open arm of junction must block crossing pipes."
