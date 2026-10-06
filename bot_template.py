"""
Pipeline Hackathon - Starter Bot Template
"""
import random
from typing import Any, Dict
from pipeline.sdk.pipeline_api import Game

def solve(game: Game) -> None:
    """
    Your main entry point. The engine will call this function and pass a `Game` object.
    
    The Game object contains:
    - game.pieces (list of dicts)
    - game.obstacles (list of dicts)
    - game.source (x, y tuple)
    - game.sink (x, y tuple)
    """
    
    # Let's make a naive random bot that just grabs random pieces and tries to place them.
    # We'll create a list of piece IDs to keep track of what we have left.
    remaining_pieces = [piece["id"] for piece in game.pieces]
    
    while remaining_pieces:
        # Pick a random piece from our inventory
        piece_id = random.choice(remaining_pieces)
        
        # Test if this piece fits at the current pipe end without colliding
        # (This is a 0-cost lookahead!)
        collides = game.would_collide(piece_id, arm=0)
        
        if not collides:
            # If it fits, commit to placing it!
            result = game.place(piece_id, arm=0)
            
            # Did we successfully reach the sink?
            if result.get("solved"):
                print("We connected the pipeline!")
                return
                
        # Remove the piece from our local inventory so we don't try it again
        remaining_pieces.remove(piece_id)
        
    print("Out of pieces or stuck!")
