"""Runner for a single submission on a single puzzle."""

import argparse
import json
import os
import subprocess
import select
import sys
import time
from typing import Any, Dict
from pipeline.engine.game import GameEngine
from pipeline.generator.generate import generate_puzzle
from pipeline.runner.protocol import send_message, read_message


def run_reference(
    seed: int,
    difficulty: str = "medium",
) -> Dict[str, Any]:
    """Run the puzzle's own solution path through the engine (proves solvability)."""
    puzzle = generate_puzzle(seed=seed, difficulty=difficulty)
    engine = GameEngine(puzzle)
    for step in puzzle.solution_path:
        pid = step["piece_id"]
        arm = step.get("chosen_arm")
        engine.place(pid, arm=arm)
    return {
        "solved": engine.is_solved,
        "steps_total": engine.steps_total,
        "steps_legal": engine.steps_legal,
        "replay_log": engine.get_replay_log(),
    }


def run_submission(
    submission_path: str,
    seed: int,
    difficulty: str = "medium",
    timeout: float = 120.0,
) -> Dict[str, Any]:
    """Run a submission in an isolated process and return the result."""
    # Generate puzzle in the parent process (secrets stay here)
    puzzle = generate_puzzle(seed=seed, difficulty=difficulty)
    engine = GameEngine(puzzle)
    
    # Launch submission
    cmd = [sys.executable, "-m", "pipeline.sdk.client", submission_path]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    
    start_time = time.time()
    status = "SOLVED"
    
    try:
        # Send initial snapshot (geometry only, no solution or seed)
        send_message({"type": "init", "data": puzzle.to_api_dict()}, stream=proc.stdin)
        
        while True:
            # Check timeout
            elapsed = time.time() - start_time
            time_left = timeout - elapsed
            if time_left <= 0:
                proc.kill()
                status = "ELIMINATED (timeout)"
                break
                
            ready, _, _ = select.select([proc.stdout], [], [], time_left)
            if not ready:
                proc.kill()
                status = "ELIMINATED (timeout)"
                break
                
            msg = read_message(stream=proc.stdout)
            if msg is None:
                # EOF reached
                if not engine.is_solved:
                    status = "ELIMINATED (crash)"
                break
                
            msg_type = msg.get("type")
            
            if msg_type == "place":
                res = engine.place(msg["piece_id"], msg.get("arm"))
                send_message({"type": "place_reply", **res}, stream=proc.stdin)
            elif msg_type == "would_collide":
                collides = engine.would_collide(msg["piece_id"], msg.get("arm"))
                send_message({"type": "would_collide_reply", "collides": collides}, stream=proc.stdin)
            elif msg_type == "done":
                break
            elif msg_type == "error":
                status = "ELIMINATED (crash)"
                break
                
    except Exception:
        status = "ELIMINATED (crash)"
        proc.kill()
        
    cpu_time = time.time() - start_time
    
    # Ensure process ends
    if proc.poll() is None:
        try:
            proc.communicate(timeout=1.0)
        except subprocess.TimeoutExpired:
            proc.kill()
            
    if not engine.is_solved and status == "SOLVED":
        status = "ELIMINATED (crash)"  # exited normally but didn't solve
        
    return {
        "solved": engine.is_solved,
        "steps_total": engine.steps_total,
        "steps_legal": engine.steps_legal,
        "steps_illegal": engine.steps_illegal,
        "cpu_time": cpu_time,
        "status": status,
        "replay_log": engine.get_replay_log()
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("submission", type=str, nargs="?", default=None)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--difficulty", type=str, default="medium")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--out", type=str, default=None, help="Output JSON path")
    parser.add_argument("--reference", action="store_true",
                        help="Run puzzle's own solution path (guaranteed solved)")
    args = parser.parse_args()

    if args.reference:
        res = run_reference(args.seed, args.difficulty)
    else:
        if not args.submission:
            parser.error("submission path required unless --reference is used")
        res = run_submission(args.submission, args.seed, args.difficulty, args.timeout)
    
    if args.out:
        with open(args.out, "w") as f:
            json.dump(res["replay_log"], f, indent=2)
        print(f"Result written to {args.out}")
    else:
        res_summary = dict(res)
        del res_summary["replay_log"]
        print(json.dumps(res_summary, indent=2))


if __name__ == "__main__":
    main()
