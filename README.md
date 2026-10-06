# Pipeline Puzzle Hackathon

Welcome to the **Pipeline Puzzle**! In this challenge, your objective is to write an autonomous bot that routes a pipeline from a **Source** to a **Sink** on a 2D grid filled with obstacles.

## Setup & Requirements
To run this project and watch the visual replays, you need:
1. **Python 3.8+** installed on your system.
2. **Pygame** installed (used by the visual replay viewer). 
   You can install it by running:
   ```bash
   pip install pygame
   ```

## The Goal
You are given a scrambled inventory of pipe pieces (straights, elbows, T-junctions, and Z-shapes) and a grid containing obstacles. You must iteratively place pieces from your inventory, extending the pipe chain step-by-step from the Source until it connects perfectly with the Sink.

## How It Works

This hackathon uses a provided Python SDK. Your bot must be written in Python and must define a `solve(game)` function. The engine will automatically load your file, instantiate a `Game` object, and pass it to your function.

### 1. The Game Object

The `game` object passed to your `solve` function contains everything you need:

- `game.grid_size`: Tuple (width, height)
- `game.source`: Tuple (x, y) starting point
- `game.sink`: Tuple (x, y) target point
- `game.pieces`: List of dictionaries representing available pipes.
- `game.obstacles`: List of dictionaries for obstacles.
- `game.chain_end`: Tuple (x, y) of the current end of the pipe.

### 2. Making Moves

The `game` object provides two critical methods for you to use:

#### Option A: Lookahead (Zero Cost)
You can ask the engine if placing a specific piece at the *current end of the pipe chain* would cause a collision (with an obstacle, or with the grid boundaries). This action does **not** cost a turn and does not consume the piece.

**Code:**
```python
collides = game.would_collide(piece_id=4, arm=0)
```
*Note: The `arm` parameter is only relevant for `junction` pieces (like T-junctions). It specifies which branch should point "forward". For straight/curved pieces, you can ignore it or pass `None`.*

#### Option B: Place Piece
Once you are confident a piece fits, you can place it. This permanently removes the piece from your inventory and advances the end of the pipe chain.

**Code:**
```python
result = game.place(piece_id=4, arm=0)

if result.get("solved"):
    print("We reached the sink!")
    return # Exit your solve function
```

## Running & Testing

A `bot_template.py` is included in this kit to get you started.

1. **Test your bot locally:**
   ```bash
   python3 -m pipeline.runner.run_submission bot_template.py --seed 12345 --difficulty easy --out replay.json
   ```

2. **Watch the Replay:**
   The runner saves your bot's game to `replay.json`. Use the included viewer to watch the simulation!
   ```bash
   python3 -m pipeline.viewer.viewer replay.json
   ```

## Tips for Success
- **Use the 1-Step Lookahead!** The `game.would_collide()` check is free. You can use it to see if your immediate next piece fits without wasting a turn on an illegal move. *(Note: Because `game.place()` is irreversible, you cannot build a deep search tree like A* using only the engine's API. For deep search, you must write your own local simulator!)*
- **Pieces just snap together.** You don't need to specify coordinates. When you place a piece, the engine automatically translates (shifts) it so its starting point snaps perfectly to the current end of your pipe chain. **Pieces are never rotated**—their orientation is strictly fixed to however they are defined in the JSON.
- **Junctions:** When placing a `junction` (e.g. a T-shape or Y-shape), the `arm` index determines which branch becomes the new "active" end of the chain. The other branches are permanently capped off.

Good luck!
