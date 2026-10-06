"""Unit tests for GameEngine step counting, legality, and solved conditions."""

import pytest
from pipeline.engine.model import Piece, Junction, Obstacle, Puzzle
from pipeline.engine.game import GameEngine


def make_simple_puzzle() -> Puzzle:
    p1 = Piece.create(id=1, end=(10, 0), curve_type="line", pipe_radius=2)
    p2 = Piece.create(id=2, end=(10, 0), curve_type="line", pipe_radius=2)
    p3 = Piece.create(id=3, end=(0, 10), curve_type="line", pipe_radius=2)
    # Obstacle at (15, 50) away from path
    obs = Obstacle.from_rect(id=100, x=15, y=50, width=5, height=5)

    return Puzzle(
        source=(10, 20),
        sink=(30, 20),
        pieces={1: p1, 2: p2, 3: p3},
        obstacles=[obs],
        grid_size=(100, 100),
    )


def test_step_accounting_exact():
    puzzle = make_simple_puzzle()
    engine = GameEngine(puzzle)

    assert engine.steps_total == 0
    assert engine.steps_legal == 0
    assert engine.steps_illegal == 0
    assert engine.game_time == 0.0

    # Read-only calls do NOT advance steps
    _ = engine.would_collide(1)
    _ = engine.remaining()
    _ = engine.get_api_snapshot()

    assert engine.steps_total == 0
    assert engine.game_time == 0.0

    # Legal placement
    res1 = engine.place(1)
    assert res1["legal"] is True
    assert res1["chain_end"] == (20, 20)
    assert res1["solved"] is False
    assert engine.steps_total == 1
    assert engine.steps_legal == 1
    assert engine.steps_illegal == 0
    assert engine.game_time == 1.0

    # Illegal placement: placing piece 1 again (already placed)
    res_dup = engine.place(1)
    assert res_dup["legal"] is False
    assert res_dup["chain_end"] == (20, 20)
    assert engine.steps_total == 2
    assert engine.steps_legal == 1
    assert engine.steps_illegal == 1
    assert engine.game_time == 2.0

    # Illegal placement: piece 3 from (20, 20) ends at (20, 30), but might be legal or illegal
    # Let's test non-existent piece ID
    res_fake = engine.place(999)
    assert res_fake["legal"] is False
    assert res_fake["chain_end"] == (20, 20)
    assert engine.steps_total == 3
    assert engine.steps_illegal == 2
    assert engine.game_time == 3.0

    # Board state unchanged by illegal moves
    assert engine.chain_end == (20, 20)
    assert 999 not in engine.placed_piece_ids
    assert engine.remaining() == [2, 3]

    # Legal placement to reach sink (30, 20)
    res2 = engine.place(2)
    assert res2["legal"] is True
    assert res2["chain_end"] == (30, 20)
    assert res2["solved"] is True
    assert engine.is_solved is True
    assert engine.steps_total == 4
    assert engine.steps_legal == 2
    assert engine.steps_illegal == 2
    assert engine.game_time == 4.0


def test_illegal_placement_leaves_board_unchanged():
    puzzle = make_simple_puzzle()
    engine = GameEngine(puzzle)

    initial_cells = set(engine.placed_cells)
    initial_chain_end = engine.chain_end
    initial_remaining = list(engine.remaining())

    # Try an illegal placement
    res = engine.place(999)
    assert res["legal"] is False
    assert engine.placed_cells == initial_cells
    assert engine.chain_end == initial_chain_end
    assert engine.remaining() == initial_remaining
    assert engine.is_solved is False


def test_snapshot_has_no_secret_flags():
    puzzle = make_simple_puzzle()
    puzzle.seed = 12345
    puzzle.solution_path = [{"piece_id": 1}, {"piece_id": 2}]

    engine = GameEngine(puzzle)
    snapshot = engine.get_api_snapshot()

    assert "seed" not in snapshot
    assert "solution_path" not in snapshot
    assert "solution" not in snapshot
    for piece in snapshot["pieces"]:
        assert "waste" not in piece
        assert "decoy" not in piece
        assert "is_solution" not in piece
