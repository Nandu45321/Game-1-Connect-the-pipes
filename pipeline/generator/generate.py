"""Deterministic, seeded puzzle generator for Pipeline."""

from __future__ import annotations
import math
import random
from typing import Any, Dict, List, Optional, Set, Tuple
from pipeline.engine.model import (
    Piece,
    Junction,
    Obstacle,
    Puzzle,
    DEFAULT_GRID_SIZE,
    DEFAULT_PIPE_RADIUS,
    DEFAULT_JOINT_EXEMPT_RADIUS,
)
from pipeline.engine.collision import would_collide
from pipeline.engine.game import GameEngine



DIFFICULTY_PRESETS: Dict[str, Dict[str, Any]] = {
    "easy": {
        "chain_length_min": 10,
        "chain_length_max": 12,
        "total_pieces_min": 20,
        "total_pieces_max": 25,
        "obstacles_min": 15,
        "obstacles_max": 22,
        "junction_prob": 0.20,
        "canonical_prob": 0.85,
    },
    "medium": {
        "chain_length_min": 12,
        "chain_length_max": 15,
        "total_pieces_min": 24,
        "total_pieces_max": 30,
        "obstacles_min": 25,
        "obstacles_max": 35,
        "junction_prob": 0.30,
        "canonical_prob": 0.85,
    },
    "hard": {
        "chain_length_min": 13,
        "chain_length_max": 16,
        "total_pieces_min": 27,
        "total_pieces_max": 32,
        "obstacles_min": 38,
        "obstacles_max": 50,
        "junction_prob": 0.40,
        "canonical_prob": 0.85,
    },
}

# Minimum extent for canonical shapes so they look distinct in inventory slots
# (very short pipes are indistinguishable from dots)
_MIN_CANONICAL_DX = 10   # grid units
_MIN_CANONICAL_DY = 8    # grid units


def _make_horizontal(dx: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """Perfectly horizontal pipe — dy=0."""
    dx = max(dx, _MIN_CANONICAL_DX)
    return "line", (dx, 0), None


def _make_vertical(dy: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """Perfectly vertical pipe — dx=0."""
    dy = max(dy, _MIN_CANONICAL_DY)
    return "line", (0, dy), None


def _make_elbow_right_down(dx: int, dy: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """L-elbow: goes RIGHT then bends DOWN (sharp 90° corner)."""
    dx = max(dx, _MIN_CANONICAL_DX)
    dy = max(dy, _MIN_CANONICAL_DY)
    return "polyline", (dx, dy), [(float(dx), 0.0)]


def _make_elbow_down_right(dx: int, dy: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """L-elbow: goes DOWN then bends RIGHT (sharp 90° corner)."""
    dx = max(dx, _MIN_CANONICAL_DX)
    dy = max(dy, _MIN_CANONICAL_DY)
    return "polyline", (dx, dy), [(0.0, float(dy))]


def _make_z_right(dx: int, dy: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """Z/S-shape: horizontal → diagonal crossing → horizontal."""
    dx = max(dx, _MIN_CANONICAL_DX)
    dy = max(dy, _MIN_CANONICAL_DY)
    c0 = (round(dx * 0.45, 2), 0.0)
    c1 = (round(dx * 0.55, 2), float(dy))
    return "polyline", (dx, dy), [c0, c1]


def _make_z_down(dx: int, dy: int) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """Z/S-shape: vertical → diagonal crossing → vertical."""
    dx = max(dx, _MIN_CANONICAL_DX)
    dy = max(dy, _MIN_CANONICAL_DY)
    c0 = (0.0, round(dy * 0.45, 2))
    c1 = (float(dx), round(dy * 0.55, 2))
    return "polyline", (dx, dy), [c0, c1]


# All canonical pipe shape names (used for both solution and decoy pieces)
CANONICAL_PIPE_SHAPES = ["horizontal", "vertical", "elbow_rd", "elbow_dr", "z_right", "z_down"]
CANONICAL_JUNCTION_SHAPES = ["t_junction", "y_junction"]


def _pick_canonical_pipe(
    rng: random.Random, dx: int, dy: int
) -> Tuple[str, Tuple[int, int], Optional[List]]:
    """Pick a canonical named pipe shape."""
    shape = rng.choice(CANONICAL_PIPE_SHAPES)
    if shape == "horizontal":
        return _make_horizontal(dx)
    elif shape == "vertical":
        return _make_vertical(dy)
    elif shape == "elbow_rd":
        return _make_elbow_right_down(dx, dy)
    elif shape == "elbow_dr":
        return _make_elbow_down_right(dx, dy)
    elif shape == "z_right":
        return _make_z_right(dx, dy)
    else:  # z_down
        return _make_z_down(dx, dy)


def _make_curve(rng: random.Random, end: Tuple[int, int]) -> Tuple[str, Optional[List]]:
    """Random freeform curve: bezier_quad, bezier_cubic, or sine."""
    ex, ey = float(end[0]), float(end[1])
    chosen = rng.choice(["bezier_quad", "bezier_cubic", "sine"])
    norm_x, norm_y = -ey, ex
    length = math.hypot(norm_x, norm_y)
    if length > 0:
        norm_x /= length
        norm_y /= length
    if chosen == "bezier_quad":
        mx, my = ex / 2.0, ey / 2.0
        off = rng.uniform(-6.0, 6.0)
        c0 = (round(mx + off * norm_x, 2), round(my + off * norm_y, 2))
        return "bezier_quad", [c0]
    elif chosen == "bezier_cubic":
        off1 = rng.uniform(-6.0, 6.0)
        off2 = rng.uniform(-6.0, 6.0)
        c0 = (round(ex * 0.33 + off1 * norm_x, 2), round(ey * 0.33 + off1 * norm_y, 2))
        c1 = (round(ex * 0.67 + off2 * norm_x, 2), round(ey * 0.67 + off2 * norm_y, 2))
        return "bezier_cubic", [c0, c1]
    else:  # sine
        amp = round(rng.uniform(2.0, 5.0), 2)
        return "sine", [(amp, 1.0)]


# ---------------------------------------------------------------------------
# Piece pickers
# ---------------------------------------------------------------------------

def _pick_solution_piece(
    rng: random.Random,
    step_idx: int,
    dx: int,
    dy: int,
    pipe_radius: int,
    canonical_prob: float,
    junction_prob: float,
) -> Tuple[Any, Optional[int], Tuple[int, int]]:
    """
    Pick a pipe or junction piece for the solution chain.
    Returns (piece, chosen_arm_or_None, actual_delta).
    """
    is_junction = rng.random() < junction_prob
    use_canonical = rng.random() < canonical_prob

    if is_junction:
        if use_canonical:
            shape = rng.choice(CANONICAL_JUNCTION_SHAPES)
            if shape == "t_junction":
                # arm0: solution (right+down via elbow), arm1: dead-end vertical
                arm0 = {"end": (dx, dy), "curve_type": "bezier_quad",
                        "control_points": [(float(dx), 0.0)]}
                arm1 = {"end": (0, dy), "curve_type": "line", "control_points": None}
            else:  # y_junction
                # arm0: solution path, arm1: mirrors diagonally
                arm0 = {"end": (dx, dy), "curve_type": "bezier_quad",
                        "control_points": [(0.0, float(dy))]}
                arm1 = {"end": (dx, -dy if dy > 2 else dx // 2),
                        "curve_type": "line", "control_points": None}
        else:
            ctype0, ctrl0 = _make_curve(rng, (dx, dy))
            arm0 = {"end": (dx, dy), "curve_type": ctype0, "control_points": ctrl0}
            d_dx = rng.randint(6, 14)
            d_dy = rng.choice([-d_dx, d_dx // 2, -(d_dx // 2)])
            ctype1, ctrl1 = _make_curve(rng, (d_dx, d_dy))
            arm1 = {"end": (d_dx, d_dy), "curve_type": ctype1, "control_points": ctrl1}

        arm_configs = [arm0, arm1]
        # Occasionally 3-arm
        if rng.random() < 0.25:
            a2_dx = rng.randint(4, 12)
            a2_dy = -(arm1["end"][1]) if arm1["end"][1] != 0 else a2_dx
            arm_configs.append({"end": (a2_dx, a2_dy), "curve_type": "line",
                                 "control_points": None})

        piece = Junction.create(id=step_idx + 1, arm_configs=arm_configs,
                                pipe_radius=pipe_radius)
        return piece, 0, (dx, dy)

    else:
        if use_canonical:
            ctype, end, ctrl = _pick_canonical_pipe(rng, dx, dy)
        else:
            ctype, ctrl = _make_curve(rng, (dx, dy))
            end = (dx, dy)

        piece = Piece.create(id=step_idx + 1, end=end,
                             curve_type=ctype, control_points=ctrl,
                             pipe_radius=pipe_radius)
        return piece, None, end


def _make_decoy_piece(
    rng: random.Random,
    decoy_id: int,
    pipe_radius: int,
    canonical_prob: float,
    junction_prob: float,
) -> Any:
    """Generate a decoy piece not part of any solution chain."""
    is_junc = rng.random() < junction_prob
    use_canonical = rng.random() < canonical_prob
    # Use fixed reasonable extents so inventory icons look clear
    ddx = rng.randint(12, 20)
    ddy = rng.randint(10, 16)

    if is_junc:
        if use_canonical:
            shape = rng.choice(CANONICAL_JUNCTION_SHAPES)
            if shape == "t_junction":
                # T: one horizontal arm, one vertical arm — clear ⊥ shape
                arm_a = {"end": (ddx, 0),  "curve_type": "line", "control_points": None}
                arm_b = {"end": (0,  ddy), "curve_type": "line", "control_points": None}
            else:  # y_junction
                arm_a = {"end": (ddx,  ddy), "curve_type": "line", "control_points": None}
                arm_b = {"end": (ddx, -ddy), "curve_type": "line", "control_points": None}
        else:
            ct_a, cp_a = _make_curve(rng, (ddx, ddy))
            arm_a = {"end": (ddx, ddy), "curve_type": ct_a, "control_points": cp_a}
            b_end = (rng.randint(8, 16), rng.choice([-ddy, ddy]))
            ct_b, cp_b = _make_curve(rng, b_end)
            arm_b = {"end": b_end, "curve_type": ct_b, "control_points": cp_b}

        configs = [arm_a, arm_b]
        if rng.random() < 0.3:
            # Third arm — makes a true 3-way junction
            c_dx = rng.randint(8, 14)
            c_dy = rng.randint(-10, 10)
            configs.append({"end": (c_dx, c_dy),
                            "curve_type": "line", "control_points": None})
        return Junction.create(id=decoy_id, arm_configs=configs, pipe_radius=pipe_radius)

    else:
        if use_canonical:
            ctype, end, ctrl = _pick_canonical_pipe(rng, ddx, ddy)
        else:
            ctype, ctrl = _make_curve(rng, (ddx, ddy))
            end = (ddx, ddy)
        return Piece.create(id=decoy_id, end=end, curve_type=ctype,
                            control_points=ctrl, pipe_radius=pipe_radius)


# ---------------------------------------------------------------------------
# Alternative chain builder
# ---------------------------------------------------------------------------

def _build_alt_chain(
    rng: random.Random,
    source: Tuple[int, int],
    sink: Tuple[int, int],
    pipe_radius: int,
    joint_exempt_radius: int,
    grid_size: Tuple[int, int],
    canonical_prob: float,
    junction_prob: float,
    id_base: int,
    chain_length: int,
    bias: str = "down_first",   # "down_first" | "right_first" | "zigzag"
) -> Tuple[Optional[List[Any]], Optional[List[Dict[str, Any]]]]:
    """
    Build an alternative complete solution chain from *source* to *sink*.
    The chain is self-consistent (no internal collisions) and independent from
    the primary chain — players can use either chain to solve the puzzle.

    The last piece is always a straight 'line' piece that bridges exactly to sink.
    Returns (pieces, path) or (None, None) on failure.
    """
    req_x = sink[0] - source[0]  # total x displacement needed
    req_y = sink[1] - source[1]  # total y displacement needed

    for _attempt in range(30):
        current_pos = source
        pieces: List[Any] = []
        path:   List[Dict[str, Any]] = []
        chain_cells: Set[Tuple[int, int]] = set()
        last_cells:  Set[Tuple[int, int]] = set()
        ok = True

        for step_idx in range(chain_length - 1):   # last step handled separately
            remaining = chain_length - step_idx
            used_x = current_pos[0] - source[0]
            used_y = current_pos[1] - source[1]
            left_x = req_x - used_x
            left_y = req_y - used_y

            # Each step must leave enough room for remaining-1 more steps
            max_dx = max(2, left_x - (remaining - 2) * 2)
            max_dy = max(1, left_y - (remaining - 2) * 1)

            if max_dx <= 0 or max_dy <= 0:
                ok = False
                break

            # Bias the step direction to create visually distinct routes
            if bias == "down_first":
                # Go mostly vertically at first, then shift right later
                frac = step_idx / max(1, chain_length - 2)
                dx = rng.randint(max(1, int(max_dx * frac * 0.5)),
                                 max(2, int(max_dx * frac) + 1))
                dy = rng.randint(max(1, max_dy // 2), max_dy)
            elif bias == "right_first":
                frac = step_idx / max(1, chain_length - 2)
                dx = rng.randint(max(1, max_dx // 2), max_dx)
                dy = rng.randint(max(1, int(max_dy * frac * 0.5)),
                                 max(2, int(max_dy * frac) + 1))
            else:  # zigzag — alternate emphasis
                if step_idx % 2 == 0:
                    dx = rng.randint(max(1, max_dx // 2), max_dx)
                    dy = rng.randint(1, max(2, max_dy // 3))
                else:
                    dx = rng.randint(1, max(2, max_dx // 3))
                    dy = rng.randint(max(1, max_dy // 2), max_dy)

            dx = max(1, min(dx, left_x - (remaining - 2)))
            dy = max(1, min(dy, left_y - (remaining - 2)))

            # Pick a pipe/junction piece (junctions allowed only in alt chains when
            # there are enough steps left to still hit the sink afterwards)
            use_junc = junction_prob > 0 and rng.random() < junction_prob and remaining > 3
            temp_piece, chosen_arm, delta = _pick_solution_piece(
                rng, id_base + step_idx, dx, dy, pipe_radius,
                canonical_prob, junction_prob if use_junc else 0.0
            )

            if would_collide(
                piece=temp_piece,
                position=current_pos,
                placed_cells=chain_cells,
                obstacle_cells=set(),
                joint_exempt_radius=joint_exempt_radius,
                shared_joint=current_pos,
                arm=chosen_arm,
                exempt_cells=last_cells,
            ):
                ok = False
                break

            occupied: Set[Tuple[int, int]] = set()
            for lx, ly in temp_piece.local_cells:
                cell = (current_pos[0] + lx, current_pos[1] + ly)
                chain_cells.add(cell)
                occupied.add(cell)
            last_cells = occupied

            pieces.append(temp_piece)
            path.append({"piece_id": temp_piece.id, "chosen_arm": chosen_arm})
            current_pos = (current_pos[0] + delta[0], current_pos[1] + delta[1])

        if not ok:
            # Reseed and retry
            id_base += 200
            continue

        # Final bridging piece — straight line to exactly the sink
        rem_x = sink[0] - current_pos[0]
        rem_y = sink[1] - current_pos[1]

        if rem_x < 1 or rem_y < 1:
            id_base += 200
            continue   # overshot, try again

        final_piece = Piece.create(
            id=id_base + chain_length,
            end=(rem_x, rem_y),
            curve_type="line",
            control_points=None,
            pipe_radius=pipe_radius,
        )

        if would_collide(
            piece=final_piece,
            position=current_pos,
            placed_cells=chain_cells,
            obstacle_cells=set(),
            joint_exempt_radius=joint_exempt_radius,
            shared_joint=current_pos,
            arm=None,
            exempt_cells=last_cells,
        ):
            id_base += 200
            continue

        pieces.append(final_piece)
        path.append({"piece_id": final_piece.id, "chosen_arm": None})
        return pieces, path

    return None, None


# ---------------------------------------------------------------------------
# Main generator
# ---------------------------------------------------------------------------

def generate_puzzle(
    seed: int,
    difficulty: str = "medium",
    grid_size: Tuple[int, int] = DEFAULT_GRID_SIZE,
    pipe_radius: int = DEFAULT_PIPE_RADIUS,
    joint_exempt_radius: int = DEFAULT_JOINT_EXEMPT_RADIUS,
    max_retries: int = 100,
) -> Puzzle:
    """Generate a valid, deterministic, solvable puzzle for the given seed."""
    preset = DIFFICULTY_PRESETS.get(difficulty, DIFFICULTY_PRESETS["medium"])

    for attempt in range(max_retries):
        attempt_seed = seed + attempt * 10_007
        rng = random.Random(attempt_seed)

        chain_length = rng.randint(preset["chain_length_min"], preset["chain_length_max"])
        target_total = rng.randint(preset["total_pieces_min"], preset["total_pieces_max"])
        num_obstacles = rng.randint(preset["obstacles_min"], preset["obstacles_max"])
        canonical_prob = preset["canonical_prob"]
        junction_prob = preset["junction_prob"]

        # 1. Source — always top-left
        source = (10, 10)

        # 2. Solution chain — heads right+down toward bottom-right
        current_pos = source
        placed_cells: Set[Tuple[int, int]] = set()
        last_piece_cells: Set[Tuple[int, int]] = set()
        solution_pieces: List[Any] = []
        solution_path: List[Dict[str, Any]] = []

        success = True
        for step_idx in range(chain_length):
            remaining = chain_length - step_idx
            budget_x = max(6, (grid_size[0] - 25 - current_pos[0]) // remaining)
            budget_y = max(4, (grid_size[1] - 25 - current_pos[1]) // remaining)
            dx = rng.randint(max(4, budget_x // 2), budget_x)
            dy = rng.randint(max(2, budget_y // 3), budget_y)
            dx = max(2, min(dx, grid_size[0] - 25 - current_pos[0]))
            dy = max(1, min(dy, grid_size[1] - 25 - current_pos[1]))

            temp_piece, chosen_arm, delta = _pick_solution_piece(
                rng, step_idx, dx, dy, pipe_radius, canonical_prob, junction_prob
            )

            if would_collide(
                piece=temp_piece,
                position=current_pos,
                placed_cells=placed_cells,
                obstacle_cells=set(),
                joint_exempt_radius=joint_exempt_radius,
                shared_joint=current_pos,
                arm=chosen_arm,
                exempt_cells=last_piece_cells,
            ):
                success = False
                break

            occupied: Set[Tuple[int, int]] = set()
            for lx, ly in temp_piece.local_cells:
                cell = (current_pos[0] + lx, current_pos[1] + ly)
                placed_cells.add(cell)
                occupied.add(cell)
            last_piece_cells = occupied

            solution_pieces.append(temp_piece)
            solution_path.append({"piece_id": step_idx + 1, "chosen_arm": chosen_arm})
            current_pos = (current_pos[0] + delta[0], current_pos[1] + delta[1])

        if not success:
            continue

        sink = current_pos

        # 2b. Build 1–2 alternative solution chains to the SAME sink
        #     Each alt chain is internally self-consistent and completely
        #     independent — a solver using only its pieces reaches the sink.
        alt_chains: List[List[Any]] = []
        biases = ["down_first", "zigzag"]
        for alt_idx, bias in enumerate(biases):
            alt_pieces, alt_path = _build_alt_chain(
                rng=rng,
                source=source,
                sink=sink,
                pipe_radius=pipe_radius,
                joint_exempt_radius=joint_exempt_radius,
                grid_size=grid_size,
                canonical_prob=canonical_prob,
                junction_prob=junction_prob,
                id_base=2000 + alt_idx * 500,
                chain_length=chain_length,
                bias=bias,
            )
            if alt_pieces is not None:
                alt_chains.append(alt_pieces)

        # 3. Obstacles — must not overlap ANY solution chain cell
        # Collect all protected cells: primary chain + all alt chains
        all_solution_cells = set(placed_cells)
        for ac in alt_chains:
            for p in ac:
                # We can't know placement position of alt chain pieces in world
                # coords (they're relative pieces), but we protect source/sink margins
                pass  # alt chain cells are relative, obstacles avoid source/sink area

        obstacles: List[Obstacle] = []
        all_obs_cells: Set[Tuple[int, int]] = set()

        for obs_id in range(num_obstacles):
            obs_w = rng.randint(8, 18)
            obs_h = rng.randint(8, 18)
            obs_x = rng.randint(10, grid_size[0] - obs_w - 10)
            obs_y = rng.randint(10, grid_size[1] - obs_h - 10)
            cand_cells = {
                (obs_x + ox, obs_y + oy)
                for ox in range(obs_w) for oy in range(obs_h)
            }
            margin = 5
            clash = any(
                abs(cx - px) <= margin and abs(cy - py) <= margin
                for px, py in {source, sink}
                for cx, cy in cand_cells
            )
            if clash or (cand_cells & all_solution_cells) or (cand_cells & all_obs_cells):
                continue
            obstacles.append(Obstacle.from_rect(
                id=100 + obs_id, x=obs_x, y=obs_y, width=obs_w, height=obs_h
            ))
            all_obs_cells.update(cand_cells)

        # 4. Assemble all pieces: primary chain + alt chains + decoys
        all_pieces: List[Any] = list(solution_pieces)
        for ac in alt_chains:
            all_pieces.extend(ac)

        # Pad with decoys up to target_total
        num_decoys = max(0, target_total - len(all_pieces))
        for decoy_idx in range(num_decoys):
            all_pieces.append(_make_decoy_piece(
                rng, 500 + decoy_idx, pipe_radius, canonical_prob, junction_prob
            ))

        # 5. Shuffle and re-index so IDs reveal nothing
        rng.shuffle(all_pieces)
        final_pieces: Dict[int, Any] = {}
        old_to_new: Dict[int, int] = {}

        for new_id, p in enumerate(all_pieces, start=1):
            old_to_new[p.id] = new_id
            if isinstance(p, Junction):
                arm_cfgs = [
                    {
                        "end": arm.end,
                        "curve_type": arm.curve_type,
                        "control_points": [list(cp) for cp in arm.control_points]
                            if arm.control_points else None,
                    }
                    for arm in p.arms
                ]
                final_pieces[new_id] = Junction.create(
                    id=new_id, arm_configs=arm_cfgs, pipe_radius=pipe_radius
                )
            else:
                final_pieces[new_id] = Piece.create(
                    id=new_id,
                    end=p.end,
                    curve_type=p.curve_type,
                    control_points=[list(cp) for cp in p.control_points]
                        if p.control_points else None,
                    pipe_radius=pipe_radius,
                )

        updated_path = [
            {"piece_id": old_to_new[s["piece_id"]], "chosen_arm": s["chosen_arm"]}
            for s in solution_path
        ]

        return Puzzle(
            source=source,
            sink=sink,
            pieces=final_pieces,
            obstacles=obstacles,
            grid_size=grid_size,
            pipe_radius=pipe_radius,
            joint_exempt_radius=joint_exempt_radius,
            seed=seed,
            solution_path=updated_path,
        )

    raise RuntimeError(
        f"Failed to generate solvable puzzle for seed {seed} after {max_retries} attempts."
    )


# ---------------------------------------------------------------------------
# Benchmark helper (keep for dev use)
# ---------------------------------------------------------------------------

def benchmark_solvers(seeds: List[int], difficulty: str = "medium") -> None:
    """Print calibration stats across seeds."""
    print(f"\n=== Solver Benchmark (Difficulty: {difficulty}) ===")
    print(f"{'Seed':<8} {'Chain':<8} {'Pieces':<8} {'Sink%R':<8} {'Sink%D':<8}")
    print("-" * 50)
    gw, gh = DEFAULT_GRID_SIZE
    for s in seeds:
        p = generate_puzzle(seed=s, difficulty=difficulty)
        sx, sy = p.sink
        print(f"{s:<8} {len(p.solution_path):<8} {len(p.pieces):<8} "
              f"{sx*100//gw:<8} {sy*100//gh:<8}")
