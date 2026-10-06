"""Pipeline pure Python game engine (no Pygame, deterministic)."""

from pipeline.engine.model import Piece, Junction, Obstacle, Puzzle, ChainState, DEFAULT_GRID_SIZE, DEFAULT_PIPE_RADIUS, DEFAULT_JOINT_EXEMPT_RADIUS, DEFAULT_UNIT_TIME
from pipeline.engine.collision import would_collide, rasterize_points_thickened
from pipeline.engine.game import GameEngine

__all__ = [
    "Piece",
    "Junction",
    "Obstacle",
    "Puzzle",
    "ChainState",
    "GameEngine",
    "would_collide",
    "rasterize_points_thickened",
    "DEFAULT_GRID_SIZE",
    "DEFAULT_PIPE_RADIUS",
    "DEFAULT_JOINT_EXEMPT_RADIUS",
    "DEFAULT_UNIT_TIME",
]
