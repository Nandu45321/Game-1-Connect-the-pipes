"""Submission runner client executing in isolated subprocess."""

from __future__ import annotations
import importlib.util
import os
import sys
from typing import Any, Dict, Optional
from pipeline.runner.protocol import send_message, read_message
from pipeline.sdk.pipeline_api import Game


def load_submission_solve(file_path: str):
    """Load solve(game) function from participant submission file."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Submission file not found: {file_path}")

    module_name = "submission_" + os.path.splitext(os.path.basename(file_path))[0]
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {file_path}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)

    if not hasattr(module, "solve"):
        raise AttributeError(f"Submission file {file_path} must expose 'def solve(game):'")

    return module.solve


def main() -> None:
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: python -m pipeline.sdk.client <submission_path>\n")
        sys.exit(1)

    submission_file = sys.argv[1]

    # Protect protocol streams from user print()
    protocol_out = sys.stdout
    protocol_in = sys.stdin
    sys.stdout = sys.stderr

    try:
        solve_func = load_submission_solve(submission_file)

        # Wait for init message from runner
        init_msg = read_message(stream=protocol_in)
        if not init_msg or init_msg.get("type") != "init":
            sys.stderr.write("Failed to receive init message from runner.\n")
            sys.exit(1)

        snapshot = init_msg["data"]

        def place_ipc(piece_id: int, arm: Optional[int]) -> Dict[str, Any]:
            send_message({"type": "place", "piece_id": piece_id, "arm": arm}, stream=protocol_out)
            reply = read_message(stream=protocol_in)
            if not reply or reply.get("type") != "place_reply":
                raise RuntimeError("Runner protocol desynchronization on place")
            return reply

        def would_collide_ipc(piece_id: int, arm: Optional[int]) -> bool:
            send_message({"type": "would_collide", "piece_id": piece_id, "arm": arm}, stream=protocol_out)
            reply = read_message(stream=protocol_in)
            if not reply or reply.get("type") != "would_collide_reply":
                raise RuntimeError("Runner protocol desynchronization on would_collide")
            return bool(reply.get("collides", True))

        game = Game(
            snapshot=snapshot,
            place_fn=place_ipc,
            would_collide_fn=would_collide_ipc,
        )

        # Execute submission
        solve_func(game)

        # Finished solving or returning
        send_message({"type": "done"}, stream=protocol_out)
        sys.exit(0)

    except Exception as exc:
        send_message({"type": "error", "error": str(exc), "error_type": type(exc).__name__}, stream=protocol_out)
        sys.exit(1)


if __name__ == "__main__":
    main()
