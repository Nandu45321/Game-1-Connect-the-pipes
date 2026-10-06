"""Rank all submissions on a set of puzzles."""

import argparse
import glob
import json
import os
import sys
from typing import Any, Dict, List
from pipeline.runner.run_submission import run_submission


def run_ranking(
    submissions_dir: str,
    seeds: List[int],
    difficulty: str = "medium",
    timeout: float = 120.0,
) -> None:
    # Find all submissions (python files)
    submissions = glob.glob(os.path.join(submissions_dir, "*.py"))
    
    if not submissions:
        print(f"No python files found in {submissions_dir}")
        return

    results = []

    for sub in submissions:
        sub_name = os.path.basename(sub)
        print(f"Running {sub_name}...")
        total_steps = 0
        eliminated = False
        status_reason = ""
        
        for seed in seeds:
            print(f"  Seed {seed}...")
            res = run_submission(sub, seed, difficulty, timeout)
            
            if not res["solved"]:
                eliminated = True
                status_reason = res["status"]
                break
                
            total_steps += res["steps_total"]
            
        if eliminated:
            results.append({
                "name": sub_name,
                "status": status_reason,
                "total_steps": float("inf")
            })
        else:
            results.append({
                "name": sub_name,
                "status": "SOLVED",
                "total_steps": total_steps
            })

    # Sort: solved first, then by total steps
    results.sort(key=lambda x: (x["status"] != "SOLVED", x["total_steps"]))

    print("\n" + "="*50)
    print("RANKING")
    print("="*50)
    rank = 1
    for r in results:
        if r["status"] == "SOLVED":
            print(f"{rank}. {r['name']} - {r['total_steps']} steps")
            rank += 1
        else:
            print(f"-. {r['name']} - ELIMINATED ({r['status']})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("submissions_dir", type=str)
    parser.add_argument("--seeds", type=int, nargs="+", required=True)
    parser.add_argument("--difficulty", type=str, default="medium")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    
    run_ranking(args.submissions_dir, args.seeds, args.difficulty, args.timeout)

if __name__ == "__main__":
    main()
