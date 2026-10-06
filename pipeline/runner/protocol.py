"""Message protocol for communication between runner and submission subprocess."""

from __future__ import annotations
import json
import sys
from typing import Any, Dict, Optional, TextIO


def send_message(msg: Dict[str, Any], stream: Optional[TextIO] = None) -> None:
    """Send a newline-delimited JSON message and flush the stream."""
    if stream is None:
        stream = sys.stdout
    line = json.dumps(msg) + "\n"
    stream.write(line)
    stream.flush()


def read_message(stream: Optional[TextIO] = None) -> Optional[Dict[str, Any]]:
    """Read a single newline-delimited JSON message from stream. Returns None on EOF."""
    if stream is None:
        stream = sys.stdin
    line = stream.readline()
    if not line:
        return None
    line = line.strip()
    if not line:
        return None
    return json.loads(line)
