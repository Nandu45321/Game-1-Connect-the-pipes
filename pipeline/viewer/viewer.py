"""Pygame viewer for Pipeline puzzle replays — metallic pipe edition."""

import argparse
import json
import math
import os
import pygame
from typing import Any, Dict, List, Optional, Tuple

# ── Layout ────────────────────────────────────────────────────────────────────
UI_WIDTH    = 280
TRAY_HEIGHT = 180
GRID_SCALE  = 4       # pixels per grid unit
FPS         = 60

# How many grid units to treat as "one slot width" for inventory scaling.
# Pieces whose span is ≤ this fill the slot; larger pieces shrink proportionally.
INV_TYPICAL = 20.0    # grid units

# ── Colours ───────────────────────────────────────────────────────────────────
BG_DARK      = (10,  12,  16)
GRID_LINE    = (22,  26,  35)
PANEL_BG     = (16,  18,  26)
TRAY_BG      = (14,  16,  22)
TEXT_COL     = (210, 215, 230)
TEXT_DIM     = (80,  85, 105)
HIGHLIGHT    = (255, 200, 50)
SOURCE_COL   = (40,  210, 90)
SINK_COL     = (220, 60,  60)
ILLEGAL_COL  = (255, 60,  60)
SLOT_BG      = (20,  24,  34)
SLOT_BORDER  = (44,  50,  68)
CHAIN_DOT    = (255, 200, 40)

# Metallic pipe colours (grayscale to tint the texture)
PIPE_SHADOW  = (5,   8,   12)
PIPE_PLACED_BODY = (255, 255, 255)
PIPE_PLACED_HI   = (255, 255, 255)
PIPE_DEAD_BODY   = (70,  70,  70)
PIPE_DEAD_HI     = (70,  70,  70)
PIPE_INV_BODY    = (180, 180, 180)
PIPE_INV_HI      = (180, 180, 180)


# ── Asset loader ──────────────────────────────────────────────────────────────
_ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
_CACHE: Dict[str, Optional[pygame.Surface]] = {}

def _load(name: str) -> Optional[pygame.Surface]:
    if name in _CACHE:
        return _CACHE[name]
    for ext in ("png", "jpg", "jpeg"):
        p = os.path.join(_ASSET_DIR, f"{name}.{ext}")
        if os.path.exists(p):
            img = pygame.image.load(p).convert()
            _CACHE[name] = img
            return img
    _CACHE[name] = None
    return None


# ── Texture strip cache ─────────────────────────────────────────────────────
# Pre-scaled strips of the pipe texture for various diameters
_TEX_STRIP_CACHE: Dict[Tuple[str, int], pygame.Surface] = {}

def _get_tex_strip(tex: pygame.Surface, diameter: int) -> pygame.Surface:
    """Return a strip of the pipe texture scaled to `diameter` height, tiling horizontally."""
    key = (id(tex), diameter)
    if key in _TEX_STRIP_CACHE:
        return _TEX_STRIP_CACHE[key]
    # Scale texture so it's `diameter` tall, keep aspect ratio for width
    tw = tex.get_width()
    th = tex.get_height()
    scaled_w = max(diameter * 2, int(tw * diameter / th))
    strip = pygame.transform.smoothscale(tex, (scaled_w, diameter))
    _TEX_STRIP_CACHE[key] = strip
    return strip


def _render_pipe(
    surf: pygame.Surface,
    pts: List[Tuple[float, float]],
    r: int,
    body: Tuple[int,int,int],
    hi:   Tuple[int,int,int],
    tex: Optional[pygame.Surface] = None,
) -> None:
    """Draw a pipe path by rendering oriented texture strips along each segment."""
    if len(pts) < 2 or r < 1:
        return

    diameter = r * 2
    strip    = _get_tex_strip(tex, diameter) if tex else None
    strip_w  = strip.get_width() if strip else 0
    CHROMA   = (0, 254, 0)   # colorkey colour: transparent background

    for i in range(len(pts) - 1):
        x0, y0 = pts[i]
        x1, y1 = pts[i + 1]
        dx = x1 - x0
        dy = y1 - y0
        seg_len = math.hypot(dx, dy)
        if seg_len < 1:
            continue
        angle_deg = math.degrees(math.atan2(-dy, dx))

        seg_w = int(seg_len) + 2

        # Regular surface with colorkey — no SRCALPHA so texture blits are opaque
        seg_surf = pygame.Surface((seg_w, diameter))
        seg_surf.fill(CHROMA)
        seg_surf.set_colorkey(CHROMA)

        if strip:
            sx = 0
            while sx < seg_w:
                seg_surf.blit(strip, (sx, 0))
                sx += strip_w
        else:
            seg_surf.fill(body)

        # Cylindrical shading overlay (separate SRCALPHA surface, blitted on top)
        shade = pygame.Surface((seg_w, diameter), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 0))
        for row in range(diameter):
            t       = row / max(diameter - 1, 1)
            shade_t = math.sin(t * math.pi)
            alpha   = int((1.0 - shade_t) * 150)
            pygame.draw.line(shade, (0, 0, 0, alpha), (0, row), (seg_w - 1, row))
        seg_surf.blit(shade, (0, 0))

        rotated = pygame.transform.rotate(seg_surf, angle_deg)
        cx = int((x0 + x1) / 2)
        cy = int((y0 + y1) / 2)
        surf.blit(rotated, (cx - rotated.get_width() // 2,
                            cy - rotated.get_height() // 2))



def _seal_joint(
    surf: pygame.Surface,
    px: float, py: float,
    r: int,
    body: Tuple[int,int,int],
    hi:   Tuple[int,int,int],
    tex: Optional[pygame.Surface] = None,
) -> None:
    ix, iy = int(px), int(py)
    diameter = r * 2
    CHROMA = (0, 254, 0)

    disc = pygame.Surface((diameter, diameter))
    disc.fill(CHROMA)
    disc.set_colorkey(CHROMA)

    if tex:
        strip = _get_tex_strip(tex, diameter)
        disc.blit(strip, (0, 0))
    else:
        disc.fill(body)

    # Draw the circular clip directly on disc using the colorkey background
    # Everything outside the circle is already CHROMA (transparent)
    # So we just draw the disc circle region — erase outside using CHROMA
    clip_surf = pygame.Surface((diameter, diameter))
    clip_surf.fill(CHROMA)
    clip_surf.set_colorkey(CHROMA)
    # Blit disc content then erase outside circle by overdrawing with CHROMA... 
    # Simpler: just draw the disc using pygame.draw.circle on a fresh surface
    final_disc = pygame.Surface((diameter, diameter))
    final_disc.fill(CHROMA)
    final_disc.set_colorkey(CHROMA)
    if tex:
        strip = _get_tex_strip(tex, diameter)
        # Clip to circle by drawing on an SRCALPHA surface, then blit
        alpha_disc = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
        alpha_disc.fill((0, 0, 0, 0))
        alpha_disc.blit(strip, (0, 0))
        pygame.draw.circle(alpha_disc, (0, 0, 0, 0), (r, r), r, r + 2)  # erase outside
        # Can't use SRCALPHA on colorkey — use circle mask approach:
        # Draw a circle of (255,255,255) on a mask, then just draw circle on final_disc
        pygame.draw.circle(final_disc, CHROMA, (r, r), r + 1)  # clear
        # Instead just draw circle directly from strip
        for row in range(diameter):
            chord = r * r - (row - r) * (row - r)
            if chord < 0:
                continue
            half_w = int(math.sqrt(chord))
            src_x = 0
            sw = strip.get_width()
            # draw this row's pixels from strip
            strip_row = strip.subsurface((src_x, min(row, strip.get_height()-1), sw, 1))
            row_surf = pygame.transform.scale(strip_row, (half_w * 2, 1))
            final_disc.blit(row_surf, (r - half_w, row))
    else:
        pygame.draw.circle(final_disc, body, (r, r), r)

    surf.blit(final_disc, (ix - r, iy - r))


def _draw_flange(surf: pygame.Surface, x: float, y: float, r: int, is_active: bool) -> None:
    ix, iy = int(x), int(y)
    rim_col  = (170, 185, 200) if is_active else (80, 90, 100)
    dark_col = (20, 25, 30)
    
    # Outer dark outline for the flange
    pygame.draw.circle(surf, dark_col, (ix, iy), r + 5, 2)
    # The actual raised metallic ring
    pygame.draw.circle(surf, rim_col, (ix, iy), r + 3, 2)
    # Inner shadow where the pipe enters the flange
    pygame.draw.circle(surf, dark_col, (ix, iy), r + 1, 1)
    
    # Four tiny bolts around the ring
    bolt_r = r + 3
    for angle in (0, 90, 180, 270):
        rad = angle * 3.14159 / 180.0
        bx = int(ix + math.cos(rad) * bolt_r)
        by = int(iy + math.sin(rad) * bolt_r)
        bolt_col = (230, 240, 255) if is_active else (110, 110, 110)
        pygame.draw.circle(surf, bolt_col, (bx, by), 1)


def _pts_to_px(
    sampled: List[List[float]],
    origin:  Tuple[float, float],
    scale:   float,
) -> List[Tuple[float, float]]:
    ox, oy = origin
    return [((ox + p[0]) * scale, (oy + p[1]) * scale) for p in sampled]


def _piece_bbox(piece: Dict) -> Tuple[float, float, float, float]:
    all_pts: List = []
    if piece["kind"] == "junction":
        for arm in piece["arms"]:
            all_pts.extend(arm["sampled_points"])
    else:
        all_pts.extend(piece["sampled_points"])
    if not all_pts:
        return 0, 0, 1, 1
    xs = [p[0] for p in all_pts]
    ys = [p[1] for p in all_pts]
    return min(xs), min(ys), max(xs), max(ys)


def _draw_piece_in_slot(
    surf:        pygame.Surface,
    piece:       Dict,
    cx: int, cy: int,
    slot_inner:  int,      # inner usable size
    pipe_radius: float,
    body:        Tuple[int,int,int],
    hi:          Tuple[int,int,int],
    pipe_tex:    Optional[pygame.Surface] = None,
) -> None:
    """
    Draw a piece preview centred at (cx, cy).
    Scale is UNIFORM: INV_TYPICAL grid units → slot_inner pixels.
    Pipe radius is capped so tiny pieces don't become blobs.
    """
    minx, miny, maxx, maxy = _piece_bbox(piece)

    # Use the larger of the two dimensions as the normaliser so the piece
    # always fits horizontally AND vertically without over-scaling.
    max_span = max(maxx - minx, maxy - miny, 0.01)
    scale = (slot_inner * 0.85) / max(max_span, INV_TYPICAL)

    mid_x = (minx + maxx) / 2.0
    mid_y = (miny + maxy) / 2.0

    r = min(int(pipe_radius * scale), slot_inner // 6)   # hard cap
    r = max(1, r)

    sw, sh = slot_inner + 20, slot_inner + 20
    slot_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
    slot_surf.fill((0, 0, 0, 0))

    def to_px(pts):
        return [(sw // 2 + (p[0] - mid_x) * scale, sh // 2 + (p[1] - mid_y) * scale)
                for p in pts]

    if piece["kind"] == "junction":
        for arm in piece["arms"]:
            _render_pipe(slot_surf, to_px(arm["sampled_points"]), r, body, hi, pipe_tex)
        _seal_joint(slot_surf, sw // 2, sh // 2, r, body, hi, pipe_tex)
    else:
        _render_pipe(slot_surf, to_px(piece["sampled_points"]), r, body, hi, pipe_tex)

    if piece["kind"] == "junction":
        _draw_flange(slot_surf, sw // 2, sh // 2, r, body == PIPE_PLACED_BODY)

    surf.blit(slot_surf, (cx - sw // 2, cy - sh // 2))


# ── Obstacle surface (pre-rendered, tiled texture) ────────────────────────────

def _build_obs_surf(puzzle: Dict, board_w: int, board_h: int) -> pygame.Surface:
    obs_tex = _load("obstacle")
    surf = pygame.Surface((board_w, board_h), pygame.SRCALPHA)
    surf.fill((0, 0, 0, 0))

    for obs in puzzle.get("obstacles", []):
        cells = obs.get("cells", [])
        if not cells:
            continue
        xs = [c[0] for c in cells]
        ys = [c[1] for c in cells]
        rx = min(xs) * GRID_SCALE
        ry = min(ys) * GRID_SCALE
        rw = (max(xs) - min(xs) + 1) * GRID_SCALE
        rh = (max(ys) - min(ys) + 1) * GRID_SCALE

        rect = pygame.Rect(rx, ry, rw, rh)

        # Drop shadow for the obstacle
        shadow = pygame.Surface((rw, rh), pygame.SRCALPHA)
        shadow.fill((0, 0, 0, 180))
        surf.blit(shadow, (rx + 4, ry + 4))

        if obs_tex:
            # Scale texture to fit the obstacle block (one tile per block)
            tile = pygame.transform.smoothscale(obs_tex, (rw, rh))
            # Darken
            dark = pygame.Surface((rw, rh), pygame.SRCALPHA)
            dark.fill((0, 0, 0, 80))
            tile.blit(dark, (0, 0))
            surf.blit(tile, (rx, ry))
        else:
            pygame.draw.rect(surf, (45, 45, 50, 240), rect)

        # Crisp inner highlight and outer border for depth
        pygame.draw.rect(surf, (70, 75, 85, 230), rect, 1)
        pygame.draw.rect(surf, (15, 15, 20, 255), rect, 2)

    return surf


# ── Viewer ────────────────────────────────────────────────────────────────────

class Viewer:
    def __init__(self, log_path: str):
        pygame.init()

        with open(log_path) as f:
            self.data = json.load(f)
        if "replay_log" in self.data:
            self.data = self.data["replay_log"]

        self.puzzle = self.data["puzzle"]
        self.events  = self.data.get("events", [])
        self.history = self.data.get("history", [])

        gw, gh = self.puzzle["grid_size"]
        self.pipe_r: int = self.puzzle["pipe_radius"]

        self.board_w = gw * GRID_SCALE
        self.board_h = gh * GRID_SCALE
        self.screen_w = self.board_w + UI_WIDTH
        self.screen_h = self.board_h + TRAY_HEIGHT

        self.screen = pygame.display.set_mode((self.screen_w, self.screen_h))
        pygame.display.set_caption("Pipeline Viewer")
        self.clock  = pygame.time.Clock()
        self.font_l = pygame.font.SysFont("monospace", 18, bold=True)
        self.font_m = pygame.font.SysFont("monospace", 15)
        self.font_s = pygame.font.SysFont("monospace", 12)

        self._bg      = self._make_bg()
        self._obs     = _build_obs_surf(self.puzzle, self.board_w, self.board_h)

        self.pipe_tex_raw = _load("pipe")
        if self.pipe_tex_raw:
            self.pipe_tex_board = pygame.Surface((self.board_w, self.board_h))
            for y in range(0, self.board_h, self.pipe_tex_raw.get_height()):
                for x in range(0, self.board_w, self.pipe_tex_raw.get_width()):
                    self.pipe_tex_board.blit(self.pipe_tex_raw, (x, y))
        else:
            self.pipe_tex_board = None
            
        self.source_tex = _load("source")
        self.sink_tex = _load("sink")

        self.step    = 0
        self.playing = False
        self.speed   = 3.0
        self.timer   = 0.0
        self.flash   = 0.0

    def _make_bg(self) -> pygame.Surface:
        s = pygame.Surface((self.board_w, self.board_h))
        cx, cy = self.board_w / 2, self.board_h / 2
        max_dist = math.hypot(cx, cy)
        
        # Radial vignette background (backlit blueprint feel)
        for y in range(0, self.board_h, 4):
            for x in range(0, self.board_w, 4):
                dist = math.hypot(x - cx, y - cy)
                factor = max(0, 1 - (dist / max_dist)**1.5)
                r = int(10 + 20 * factor)
                g = int(14 + 26 * factor)
                b = int(22 + 35 * factor)
                pygame.draw.rect(s, (r, g, b), (x, y, 4, 4))
                
        # Subtle grid lines
        for x in range(0, self.board_w, GRID_SCALE * 10):
            pygame.draw.line(s, (35, 42, 60), (x, 0), (x, self.board_h))
        for y in range(0, self.board_h, GRID_SCALE * 10):
            pygame.draw.line(s, (35, 42, 60), (0, y), (self.board_w, y))
        return s

    def _txt(self, text, x, y, font=None, color=TEXT_COL):
        img = (font or self.font_m).render(text, True, color)
        self.screen.blit(img, (x, y))

    def _placed_ids_at(self, step: int) -> set:
        ids = set()
        for i in range(step):
            ev = self.events[i]
            if ev.get("legal"):
                ids.add(ev["piece_id"])
        return ids

    def _hist_map(self) -> Dict[int, Dict]:
        return {h["piece_id"]: h for h in self.history}

    # ── render ────────────────────────────────────────────────────────────────
    def render(self):
        self.screen.fill(BG_DARK)
        self.screen.blit(self._bg, (0, 0))
        self.screen.blit(self._obs, (0, 0))

        placed_ids = self._placed_ids_at(self.step)
        hist       = self._hist_map()
        pipe_r_px  = self.pipe_r * GRID_SCALE

        # ── Source
        sx, sy = self.puzzle["source"]
        spx = (int(sx * GRID_SCALE), int(sy * GRID_SCALE))
        icon_r = pipe_r_px + 7
        
        # Glow
        pygame.draw.circle(self.screen, (30, 150, 60), spx, icon_r + 6)
        
        if self.source_tex:
            s_scaled = pygame.transform.smoothscale(self.source_tex, (icon_r*2, icon_r*2))
            s_scaled.fill((100, 100, 100), special_flags=pygame.BLEND_RGB_ADD)
            self.screen.blit(s_scaled, (spx[0] - icon_r, spx[1] - icon_r))
        else:
            pygame.draw.circle(self.screen, PIPE_SHADOW, spx, icon_r + 4)
            pygame.draw.circle(self.screen, SOURCE_COL, spx, icon_r)
            self._txt("S", spx[0]-5, spx[1]-8, self.font_s, (0,0,0))
            
        pygame.draw.circle(self.screen, (100, 255, 150), spx, icon_r, 2)

        # ── Sink
        dx, dy = self.puzzle["sink"]
        dpx = (int(dx * GRID_SCALE), int(dy * GRID_SCALE))
        
        # Glow
        pygame.draw.circle(self.screen, (150, 40, 40), dpx, icon_r + 6)
        
        if self.sink_tex:
            d_scaled = pygame.transform.smoothscale(self.sink_tex, (icon_r*2, icon_r*2))
            d_scaled.fill((100, 100, 100), special_flags=pygame.BLEND_RGB_ADD)
            self.screen.blit(d_scaled, (dpx[0] - icon_r, dpx[1] - icon_r))
        else:
            pygame.draw.circle(self.screen, PIPE_SHADOW, dpx, icon_r + 4)
            pygame.draw.circle(self.screen, SINK_COL, dpx, icon_r)
            self._txt("D", dpx[0]-5, dpx[1]-8, self.font_s, (0,0,0))
            
        pygame.draw.circle(self.screen, (255, 100, 100), dpx, icon_r, 2)

        # ── Placed pipes ──────────────────────────────────────────────────────
        pipe_layer = pygame.Surface((self.board_w, self.board_h), pygame.SRCALPHA)
        pipe_layer.fill((0, 0, 0, 0))

        joint_pts: List[Tuple[float, float]] = []

        for pid in placed_ids:
            h = hist.get(pid)
            if not h:
                continue
            pos     = h["position"]
            piece   = next((p for p in self.puzzle["pieces"] if p["id"] == pid), None)
            if not piece:
                continue
            chosen  = h.get("chosen_arm")

            if piece["kind"] == "junction":
                for arm in piece["arms"]:
                    pts  = _pts_to_px(arm["sampled_points"], pos, GRID_SCALE)
                    used = (arm["arm_id"] == chosen)
                    body = PIPE_PLACED_BODY if used else PIPE_DEAD_BODY
                    hi   = PIPE_PLACED_HI   if used else PIPE_DEAD_HI
                    _render_pipe(pipe_layer, pts, pipe_r_px, body, hi, self.pipe_tex_raw)
                ox, oy = pos
                joint_pts.append((ox * GRID_SCALE, oy * GRID_SCALE))
            else:
                pts = _pts_to_px(piece["sampled_points"], pos, GRID_SCALE)
                _render_pipe(pipe_layer, pts, pipe_r_px,
                             PIPE_PLACED_BODY, PIPE_PLACED_HI, self.pipe_tex_raw)

            # Collect joint seam points
            ox, oy = pos
            joint_pts.append((ox * GRID_SCALE, oy * GRID_SCALE))
            ce = h.get("chain_end_after")
            if ce:
                joint_pts.append((ce[0] * GRID_SCALE, ce[1] * GRID_SCALE))

        # Seal all joints
        for jx, jy in joint_pts:
            _seal_joint(pipe_layer, jx, jy, pipe_r_px,
                        PIPE_PLACED_BODY, PIPE_PLACED_HI, self.pipe_tex_raw)

        self.screen.blit(pipe_layer, (0, 0))

        # Draw mechanical flanges over the textured pipes at the joints
        for jx, jy in joint_pts:
            _draw_flange(self.screen, jx, jy, pipe_r_px, True)

        # ── Chain-end marker
        if self.step > 0:
            ev = self.events[self.step - 1]
            ce = ev.get("chain_end")
            if ce:
                cpx = (int(ce[0] * GRID_SCALE), int(ce[1] * GRID_SCALE))
                pygame.draw.circle(self.screen, CHAIN_DOT, cpx, pipe_r_px + 4)
                pygame.draw.circle(self.screen, PIPE_SHADOW, cpx, pipe_r_px + 4, 2)

        # ── Illegal flash
        if self.flash > 0:
            ov = pygame.Surface((self.board_w, self.board_h), pygame.SRCALPHA)
            a  = int(min(200, (self.flash / 0.4) * 200))
            ov.fill((255, 30, 30, a))
            self.screen.blit(ov, (0, 0))

        # ── Info panel ────────────────────────────────────────────────────────
        px = self.board_w + 12
        pygame.draw.rect(self.screen, PANEL_BG,
                         pygame.Rect(self.board_w, 0, UI_WIDTH, self.screen_h))
        pygame.draw.line(self.screen, (40, 46, 62),
                         (self.board_w, 0), (self.board_w, self.screen_h), 2)

        self._txt("PIPELINE VIEWER", px, 18, self.font_l, HIGHLIGHT)
        self._txt(f"Step   : {self.step} / {len(self.events)}", px, 55)
        self._txt(f"Speed  : {self.speed:.1f}x",                px, 73)
        self._txt(f"Placed : {len(placed_ids)} / {len(self.puzzle['pieces'])}",
                  px, 91)

        if self.step > 0:
            ev    = self.events[self.step - 1]
            t     = ev.get("game_time", 0)
            legal = ev.get("legal", True)
            self._txt(f"Time   : {t:.1f}s", px, 116)
            col = TEXT_COL if legal else ILLEGAL_COL
            self._txt("[OK] LEGAL" if legal else "[X] ILLEGAL", px, 134, color=col)
            if not legal and ev.get("reason"):
                self._txt(ev["reason"][:28], px, 152, self.font_s, ILLEGAL_COL)

        solved = self.data.get("summary", {}).get("solved", False)
        if solved and self.step == len(self.events):
            self._txt("*** SOLVED! ***", px, 178, self.font_l, SOURCE_COL)

        self._txt("-- Controls --",     px, 225, self.font_s, TEXT_DIM)
        self._txt("Space : Play/Pause", px, 241, self.font_s, TEXT_DIM)
        self._txt("<-/-> : Step",       px, 257, self.font_s, TEXT_DIM)
        self._txt("Up/Dn : Speed",      px, 273, self.font_s, TEXT_DIM)
        self._txt("R     : Restart",    px, 289, self.font_s, TEXT_DIM)

        # ── Inventory tray ────────────────────────────────────────────────────
        tray_r = pygame.Rect(0, self.board_h, self.board_w, TRAY_HEIGHT)
        pygame.draw.rect(self.screen, TRAY_BG, tray_r)
        pygame.draw.line(self.screen, (40, 46, 62),
                         (0, self.board_h), (self.board_w, self.board_h), 2)

        self._txt("v  INVENTORY - pieces remaining",
                  10, self.board_h + 6, self.font_m, HIGHLIGHT)

        all_pcs = self.puzzle["pieces"]
        SLOT    = 64
        COLS    = max(1, (self.board_w - 8) // SLOT)
        INNER_Y = self.board_h + 26

        for idx, piece in enumerate(all_pcs):
            col_i = idx % COLS
            row_i = idx // COLS
            sx_s  = 4 + col_i * SLOT
            sy_s  = INNER_Y + row_i * SLOT
            if sy_s + SLOT > self.screen_h:
                break

            is_placed  = piece["id"] in placed_ids
            slot_rect  = pygame.Rect(sx_s, sy_s, SLOT - 3, SLOT - 3)
            bg = (28, 16, 16) if is_placed else SLOT_BG
            pygame.draw.rect(self.screen, bg, slot_rect, border_radius=5)
            pygame.draw.rect(self.screen, SLOT_BORDER, slot_rect, 1, border_radius=5)

            body = PIPE_DEAD_BODY if is_placed else PIPE_INV_BODY
            hi   = PIPE_DEAD_HI   if is_placed else PIPE_INV_HI
            _draw_piece_in_slot(
                self.screen, piece,
                sx_s + (SLOT - 3) // 2,
                sy_s + (SLOT - 3) // 2,
                SLOT - 14,
                self.pipe_r,
                body, hi,
                self.pipe_tex_raw
            )

            if is_placed:
                sr = slot_rect
                pygame.draw.line(self.screen, (160, 40, 40),
                                 (sr.left + 5, sr.top + 5),
                                 (sr.right - 5, sr.bottom - 5), 2)
                pygame.draw.line(self.screen, (160, 40, 40),
                                 (sr.right - 5, sr.top + 5),
                                 (sr.left + 5, sr.bottom - 5), 2)

            self._txt(f"#{piece['id']}", sx_s + 2, sy_s + 1,
                      self.font_s, TEXT_DIM)

        pygame.display.flip()

    # ── event loop ────────────────────────────────────────────────────────────
    def run(self):
        running = True
        while running:
            dt = self.clock.tick(FPS) / 1000.0
            if self.flash > 0:
                self.flash -= dt

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False
                elif ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_SPACE:
                        self.playing = not self.playing
                    elif ev.key == pygame.K_RIGHT:
                        if self.step < len(self.events):
                            e = self.events[self.step]
                            self.step += 1
                            if not e.get("legal", True):
                                self.flash = 0.4
                    elif ev.key == pygame.K_LEFT:
                        self.step = max(0, self.step - 1)
                    elif ev.key == pygame.K_UP:
                        self.speed = min(self.speed * 1.5, 60.0)
                    elif ev.key == pygame.K_DOWN:
                        self.speed = max(self.speed / 1.5, 0.2)
                    elif ev.key == pygame.K_r:
                        self.step    = 0
                        self.playing = False

            if self.playing and self.step < len(self.events):
                self.timer += dt
                if self.timer >= 1.0 / self.speed:
                    self.timer = 0.0
                    e = self.events[self.step]
                    self.step += 1
                    if not e.get("legal", True):
                        self.flash = 0.4

            self.render()
        pygame.quit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("log", help="Path to replay JSON")
    args = parser.parse_args()
    Viewer(args.log).run()


if __name__ == "__main__":
    main()
