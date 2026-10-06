"""Procedural and Image textures for Pipeline."""

import pygame
import math
import os
from typing import Tuple, List

_assets_cache = {}
_brushes = {}

def get_asset(name: str) -> pygame.Surface:
    if name not in _assets_cache:
        path = os.path.join(os.path.dirname(__file__), "assets", f"{name}.jpg")
        if os.path.exists(path):
            img = pygame.image.load(path).convert()
            # If we need transparency, we can colorkey black
            if name in ["source", "sink"]:
                img.set_colorkey((0, 0, 0))
            _assets_cache[name] = img
        else:
            _assets_cache[name] = None
    return _assets_cache[name]

def draw_thick_curve(
    surface: pygame.Surface,
    points: List[Tuple[float, float]],
    radius: int,
    color: Tuple[int, int, int],
    outline_color: Tuple[int, int, int] = (30, 30, 30),
    is_waste: bool = False
):
    """Draw a thickened parametric curve using textures."""
    if not points:
        return

    pipe_tex = get_asset("pipe")
    if pipe_tex:
        min_x = min(p[0] for p in points) - radius
        max_x = max(p[0] for p in points) + radius
        min_y = min(p[1] for p in points) - radius
        max_y = max(p[1] for p in points) + radius
        w = int(max_x - min_x) + 2
        h = int(max_y - min_y) + 2
        
        if w <= 0 or h <= 0: return
        
        mask_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        for px, py in points:
            pygame.draw.circle(mask_surf, (255, 255, 255, 255), (int(px - min_x), int(py - min_y)), radius)
            
        tex_surf = pygame.Surface((w, h), pygame.SRCALPHA)
        tw, th = pipe_tex.get_size()
        start_x = - (int(min_x) % tw)
        start_y = - (int(min_y) % th)
        for x in range(start_x, w, tw):
            for y in range(start_y, h, th):
                tex_surf.blit(pipe_tex, (x, y))
                
        # Mask the texture to the white curve
        mask_surf.blit(tex_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
        
        # Apply color tint if it's a decoy/unselected
        if color != (100, 200, 255):  
            tint = pygame.Surface((w, h), pygame.SRCALPHA)
            tint.fill((0, 0, 0, 180))
            mask_surf.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
        # Draw outline
        for px, py in points:
            pygame.draw.circle(surface, outline_color, (int(px), int(py)), radius + 1)
            
        surface.blit(mask_surf, (min_x, min_y))
    else:
        # Fallback procedural
        for px, py in points:
            pygame.draw.circle(surface, outline_color, (int(px), int(py)), radius + 1)
        for px, py in points:
            pygame.draw.circle(surface, color, (int(px), int(py)), radius)
        highlight = (min(255, color[0] + 80), min(255, color[1] + 80), min(255, color[2] + 80))
        for px, py in points:
            pygame.draw.circle(surface, highlight, (int(px - radius*0.3), int(py - radius*0.3)), max(1, radius//2))

def create_grid_surface(width: int, height: int, cell_size: int) -> pygame.Surface:
    """Create a background grid surface."""
    surf = pygame.Surface((width, height))
    surf.fill((15, 15, 20)) # Dark background
    grid_color = (30, 30, 40)
    for x in range(0, width, cell_size):
        pygame.draw.line(surf, grid_color, (x, 0), (x, height))
    for y in range(0, height, cell_size):
        pygame.draw.line(surf, grid_color, (0, y), (width, y))
    return surf
