#!/usr/bin/env python3
"""NEON REBOUND v10 — a complete single-file game, Python 3.10+.

Install: python -m pip install "pygame>=2.6,<3" "pymunk>=7,<8"
Play: python neon_rebound.py       360 FPS: python neon_rebound.py --fps 360

A/D: move; J/L or left/right arrows: rotate; P: pause; F: FPS limit.
R: restart confirmation; Escape: exit confirmation. Skip costs 1 point and
has a 30-second cooldown. Hold B+O+L+A+Space to unlock unlimited extra balls.
The star button opens a paused archive of discovered powerups. Discoveries
persist in LocalAppData/NeonRebound/discoveries.json (not the executable).

Powerups last 15 seconds. Giant grows 20% per hit with no growth ceiling;
once physically larger than the arena it overflows visually and collects
with its full radius without trying to solve impossible wall contacts.
Fortune samples an uncapped power of two with exact geometric p=163/250.
Quantum Link couples opposite PADDLE impulses only, launches two independent
headings, then hides the real ball until paddle contact resolves the pair.
Supernova charges 3s and emits 48
gravity-free rays. Fission ends with a scoring fusion; Voronoi ends with
expanding wavefronts and a colourful laser fracture. Wormhole, Satellite,
Snell's Realm, Mobius Strip, Multiball, Overdrive, Wave-Particle Duality and
Back To The Future complete the original archive. Nine selectable trails,
including animated DNA, Spacetime, electrical discharges and magical dust.
Nine target designs have their own animated details and hit colors.
Gaussian Roll keeps its physical funnel inside the arena, then visits ten
pegs using independent fair bits and smooth hops into eleven prize pockets.
War Crime waits on a temporary platform for a fresh keypress before its 15s
of ACRO flight. Hold L/right for thrust; A/D rolls without automatic leveling.
Left drops a grenade: floor impact emits five incandescent scoring shards,
which can also destroy the drone. Arena impact likewise ends the flight.
Analytical Path freezes the ball while you enter f(x), draws f(x)-f(0) in
local Cartesian coordinates, then rides either signed x branch and collects
targets, including four temporary phantoms on the roomier side. The bottom
left editor fades when not hovered. Movement/rotation changes ask before
resetting a nonzero score.
Expressions are parsed with a restricted evaluator and bounded sampling.

Physics runs at 240 Hz with conservative substeps, swept target tests and
render interpolation; Duality trails sample at 960 Hz. Render FPS never
changes simulation speed. Long stalls discard elapsed time above 0.25s.
Powerup arrival has an exponential wait averaging 30s after completion;
Quantum observation and finishing animations complete before this wait.
Performance with very many balls depends on the computer. No external
artwork, font or sound files are required to run the script.
"""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
from functools import lru_cache
import math
import json
import os
import random
from pathlib import Path
import sys
import time

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
try:
    import pygame
    import pymunk
except ImportError as exc:
    raise SystemExit(
        'Missing dependency. Run: python -m pip install "pygame>=2.6,<3" "pymunk>=7,<8"'
    ) from exc

V = pymunk.Vec2d
WIDTH, HEIGHT = 1600, 900
DRAW_SCALE = 0.8
SCREEN_WIDTH, SCREEN_HEIGHT = WIDTH / DRAW_SCALE, HEIGHT / DRAW_SCALE
LEFT, RIGHT, TOP, BOTTOM = (v / DRAW_SCALE for v in (60.0, 1540.0, 136.0, 794.0))
FIXED_DT = 1.0 / 240.0
MAX_FRAME_DT = 0.25
BALL_RADIUS, GIANT_RADIUS = 12.0, 40.0
MAX_BALL_SPEED = 2200.0
BOOST_MAX_SPEED = 8000.0
TURBO_MIN_IMPACT = 20.0
BALL_ELASTICITY, WALL_ELASTICITY = 0.9, 0.9
GRAVITY = 700.0
PADDLE_HALF, PADDLE_RADIUS = 120.0, 8.0
MAX_ANGLE = math.pi / 4
PADDLE_Y = BOTTOM - 8 - PADDLE_HALF * math.sin(MAX_ANGLE) + 2
PADDLE_VERTICES = ((-PADDLE_HALF, 0), (-PADDLE_HALF * .65, -8),
                   (PADDLE_HALF * .65, -8), (PADDLE_HALF, 0),
                   (PADDLE_HALF * .65, 8), (-PADDLE_HALF * .65, 8))
SATELLITE_STRENGTH, SATELLITE_SOFT_RADIUS = 900_000_000.0, 150.0
SATELLITE_MAX_ACCEL = 9500.0
FUSION_DURATION, FISSION_MIN_RADIUS = .45, 3.0
WAVE_AMPLITUDE, WAVE_WAVELENGTH, WAVE_REST_FREQUENCY = 24.0, 90.0, .8
WAVE_FRAME_MAX_TURN = 24.0
WAVE_MAX_SPEED = (MAX_BALL_SPEED * (1 + 2 * math.tau * WAVE_AMPLITUDE / WAVE_WAVELENGTH)
                  + WAVE_AMPLITUDE * WAVE_FRAME_MAX_TURN + 32)
POWER_MEAN_WAIT, POWER_DURATION = 30.0, 15.0
TARGET_RADIUS, PICKUP_RADIUS = 25.0, 28.0
TRAIL_STYLES = ('ORBITS', 'TRACE', 'COMET', 'DASHES', 'OFF', 'DNA', 'SPACETIME', 'ELECTRIC', 'MAGIC')
BG, PANEL, INK, MUTED = (8, 13, 25), (16, 25, 42), (231, 242, 255), (126, 149, 175)
CYAN, PINK, GOLD = (60, 225, 235), (255, 96, 166), (255, 211, 91)
COLORS = (PINK, CYAN, GOLD, (152, 122, 255), (104, 242, 170), (255, 147, 87), (255, 48, 54))
POWERUPS = {
    "giant": ("GIANT", "Grow 20% with every target", (255, 163, 76)),
    "multiball": ("MULTIBALL", "Ten extra balls for fifteen seconds", (173, 124, 255)),
    "overdrive": ("OVERDRIVE", "Wall rebounds boost speed by 15%", (255, 68, 112)),
    "double": ("FORTUNE", "A golden star. An unlimited prize.", GOLD),
    "satellite": ("SATELLITE", "Fall into orbit around your target", (85, 233, 221)),
    "explosion": ("SUPERNOVA", "Three seconds. Forty-eight sparks.", (255, 124, 62)),
    "mobius": ("MOBIUS STRIP", "Paired portals fold the arena", (80, 161, 255)),
    "fission": ("NUCLEAR FISSION", "Split on impact. Reunite in fusion.", (107, 255, 132)),
    "duality": ("WAVE-PARTICLE DUALITY", "Ride a wave along a ballistic path", (209, 155, 255)),
    "timewarp": ("BACK TO THE FUTURE", "A future echo with ten bounces ahead", (136, 226, 255)),
    "voronoi": ("VORONOI", "Fifteen seeds fracture into light", (139, 246, 202)),
    "wormhole": ("WORMHOLE", "A spacetime shortcut to each target", (112, 183, 255)),
    "snell": ("SNELL'S REALM", "Two worlds. Two rays. One crossing.", (205, 177, 255)),
    "quantum": ("QUANTUM LINK", "Opposite impulses. One hidden truth.", (135, 163, 255)),
    "gaussian": ("GAUSSIAN ROLL", "Ten fair bounces. Eleven prize pockets.", (87, 233, 192)),
    "drone": ("WAR CRIME", "Fly ACRO. Drop grenades. Dodge shrapnel.", (255, 174, 76)),
    "analytical": ("ANALYTICAL PATH", "Write a function. Ride its curve.", (158, 200, 255)),
}


def roll_fortune(rng):
    """Exact geometric law p=163/250; no float tail or fixed prize ceiling."""
    exponent = 1
    while rng.randrange(250) >= 163:
        exponent += 1
    return 1 << exponent


def multiplier_text(value):
    return f"x{value}" if value < 10**12 else f"x2^{value.bit_length() - 1}"


def score_text(value):
    if abs(value) < 10**9:
        return f"{value:04d}"
    magnitude = abs(value)
    exponent = int(math.log10(magnitude))
    leading = magnitude // 10 ** max(0, exponent - 2)
    return f"{'-' if value < 0 else ''}{leading / 100:.2f}e{exponent}"


def resource_path(name):
    """Ruta de un recurso junto al script o incrustado por PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def nearest_on_segment(point, start, end):
    delta = end - start
    if delta.length_squared < 1e-12:
        return start
    return start + delta * clamp((point - start).dot(delta) / delta.length_squared, 0.0, 1.0)


def swept_circle(start, end, center, radius):
    return (nearest_on_segment(center, start, end) - center).length_squared <= radius * radius


def segment_aabb(start, end, x0, y0, x1, y1):
    """Interseccion segmento/caja mediante intervalos, incluidos casos paralelos."""
    t0, t1 = 0.0, 1.0
    for origin, delta, lo, hi in ((start.x, end.x - start.x, x0, x1),
                                   (start.y, end.y - start.y, y0, y1)):
        if abs(delta) < 1e-12:
            if not lo <= origin <= hi:
                return False
        else:
            a, b = sorted(((lo - origin) / delta, (hi - origin) / delta))
            t0, t1 = max(t0, a), min(t1, b)
            if t0 > t1:
                return False
    return True


def swept_square(start, end, center, half, radius):
    """Barrido exacto circulo/cuadrado: dos rectangulos y cuatro esquinas curvas."""
    x0, y0, x1, y1 = center.x - half, center.y - half, center.x + half, center.y + half
    if segment_aabb(start, end, x0 - radius, y0, x1 + radius, y1):
        return True
    if segment_aabb(start, end, x0, y0 - radius, x1, y1 + radius):
        return True
    return any(swept_circle(start, end, V(x, y), radius)
               for x in (x0, x1) for y in (y0, y1))


def star_vertices(center, radius=PICKUP_RADIUS):
    return [center + V(math.cos(-math.pi / 2 + i * math.pi / 5),
                       math.sin(-math.pi / 2 + i * math.pi / 5)) *
            (radius if i % 2 == 0 else radius * .45) for i in range(10)]


def swept_star(start, end, center, radius):
    """Estrella concava exacta: centro interior + aristas engrosadas por el radio."""
    if not swept_circle(start, end, center, PICKUP_RADIUS + radius):
        return False
    vertices = star_vertices(center)
    inside = False
    for a, b in zip(vertices, vertices[1:] + vertices[:1]):
        if (a.y > start.y) != (b.y > start.y):
            if start.x < (b.x - a.x) * (start.y - a.y) / (b.y - a.y) + a.x:
                inside = not inside
        if swept_circle(start, end, a, radius):
            return True
        edge = b - a
        length = edge.length
        along = edge / length
        normal = V(-along.y, along.x)
        p, q = start - a, end - a
        if segment_aabb(V(p.dot(along), p.dot(normal)), V(q.dot(along), q.dot(normal)),
                        0, -radius, length, radius):
            return True
    return inside


@dataclass
class Controls:
    move: int = 0
    turn: int = 0
    throttle: bool = False
    bomb: bool = False


SECRET_KEYS = (pygame.K_b, pygame.K_o, pygame.K_l, pygame.K_a, pygame.K_SPACE)


def controls_from_keys(keys):
    move = int(bool(keys[pygame.K_d])) - int(bool(keys[pygame.K_a]))
    turn = int(bool(keys[pygame.K_l] or keys[pygame.K_RIGHT])) - int(bool(keys[pygame.K_j] or keys[pygame.K_LEFT]))
    return Controls(move, turn, bool(keys[pygame.K_l] or keys[pygame.K_RIGHT]), bool(keys[pygame.K_LEFT]))


class Ball:
    def __init__(self, space, position, velocity, radius=BALL_RADIUS, temporary=False):
        self.body = pymunk.Body(1.0, pymunk.moment_for_circle(1.0, 0.0, radius))
        self.body.position, self.body.velocity = position, velocity
        self.radius, self.temporary = radius, temporary
        self.shape = self.make_shape()
        space.add(self.body, self.shape)
        self.previous = V(*position)
        self.trail = deque(maxlen=32)
        self.normal_speed = self.body.velocity.length
        self.wall_boost_count = 0
        self.fission_group = None
        self.split_ready_at = 0.0
        self.wave_active = False
        self.wave_center = V(*position)
        self.wave_velocity = V(*velocity)
        self.wave_phase = 0.0
        self.wave_axis = V(1, 0)
        self.giant_goal_radius = radius
        self.wormhole_transit = False

    def make_shape(self):
        shape = pymunk.Circle(self.body, self.radius)
        shape.elasticity, shape.friction = BALL_ELASTICITY, 0.0
        shape.collision_type = 1
        # A circle larger than the arena cannot satisfy opposing solid walls.
        # It keeps its true scoring radius and grows beyond the viewport; manual
        # containment pins exhausted axes instead of feeding impossible contacts.
        shape.sensor = self.radius * 2 >= min(RIGHT - LEFT, BOTTOM - TOP) - 17
        return shape

    def resize(self, space, radius):
        # Reemplazar la forma fuera de step invalida correctamente contactos antiguos.
        space.remove(self.shape)
        self.radius = radius
        self.body.moment = pymunk.moment_for_circle(1.0, 0.0, radius)
        self.shape = self.make_shape()
        space.add(self.shape)
        self.body.activate()

    def limit_speed(self, limit=MAX_BALL_SPEED):
        speed2 = self.body.velocity.length_squared
        if speed2 > limit * limit:
            self.body.velocity *= limit / math.sqrt(speed2)


@dataclass
class Pickup:
    kind: str
    position: V


class Projectile:
    def __init__(self, position, velocity, color=None):
        self.position = V(*position)
        self.previous = self.position
        self.velocity = V(*velocity)
        self.radius = 5.0
        self.trail = deque(maxlen=12)
        self.color = color or POWERUPS['explosion'][2]


@dataclass
class Portal:
    wall: str
    position: V
    pair_position: V
    exit_wall: str
    color: tuple
    is_entry: bool
    created_at: float
    half_length: float = 46.0

    @property
    def normal(self):
        return {"left": V(1, 0), "right": V(-1, 0),
                "top": V(0, 1), "bottom": V(0, -1)}[self.wall]

    @property
    def tangent(self):
        return V(0, 1) if self.wall in ("left", "right") else V(1, 0)


class Ghost:
    """Copia balistica independiente: el tiempo avanza tres veces mas rapido."""
    def __init__(self, ball):
        self.position = V(*ball.body.position)
        self.previous = self.position
        self.velocity = V(*ball.body.velocity)
        self.radius = ball.radius
        self.restitution = ball.shape.elasticity * WALL_ELASTICITY
        self.trail = deque(maxlen=72)
        self.age = 0.0
        self.phase = 0.0
        self.trail_clock = 0.0
        self.motion_time = 0.0
        self.wall_collisions = 0
        self.forecast_points = []
        self.forecast_impacts = []
        self.forecast_hit_pos = None
        self.forecast_revision = 0
        self._forecast_key = None
        self._forecast_records = []
        self._forecast_bounces = []
        self._forecast_target = None
        self._forecast_hit_time = None
        self._forecast_state = None


def build_voronoi(points, bounds=None):
    """Celdas convexas y aristas interiores por recorte de semiplanos.

    Quince semillas no necesitan dependencias geometricas externas. Los puntos
    repetidos mantienen su marca, pero solo el primero conserva una celda.
    """
    x0, x1, y0, y1 = bounds or (LEFT + 8, RIGHT - 8, TOP + 8, BOTTOM - 8)
    sites = [V(*point) for point in points]
    if any(not math.isfinite(p.x) or not math.isfinite(p.y) for p in sites):
        raise ValueError("Las semillas Voronoi deben tener coordenadas finitas")
    cells, edges, edge_keys = [], [], set()
    for index, site in enumerate(sites):
        if any((site - old).length_squared < 1e-12 for old in sites[:index]):
            cells.append([])
            continue
        polygon = [V(x0, y0), V(x1, y0), V(x1, y1), V(x0, y1)]
        for other in sites:
            normal = other - site
            if normal.length_squared < 1e-12:
                continue
            halfway = normal.length_squared * .5
            clipped = []
            if not polygon:
                break
            previous = polygon[-1]
            previous_distance = (previous - site).dot(normal) - halfway
            for current in polygon:
                distance = (current - site).dot(normal) - halfway
                inside, previous_inside = distance <= 1e-7, previous_distance <= 1e-7
                if inside != previous_inside:
                    fraction = previous_distance / (previous_distance - distance)
                    clipped.append(previous + (current - previous) * clamp(fraction, 0, 1))
                if inside:
                    clipped.append(current)
                previous, previous_distance = current, distance
            polygon = []
            for vertex in clipped:
                if not polygon or (vertex - polygon[-1]).length_squared > 1e-12:
                    polygon.append(vertex)
            if len(polygon) > 1 and (polygon[0] - polygon[-1]).length_squared < 1e-12:
                polygon.pop()
        cells.append(polygon)
        for start, end in zip(polygon, polygon[1:] + polygon[:1]):
            if (end - start).length_squared < 1e-10:
                continue
            on_boundary = any(abs(a - boundary) < 1e-5 and abs(b - boundary) < 1e-5
                              for a, b, boundary in ((start.x, end.x, x0), (start.x, end.x, x1),
                                                     (start.y, end.y, y0), (start.y, end.y, y1)))
            if on_boundary:
                continue
            key = tuple(sorted(((round(start.x, 5), round(start.y, 5)),
                                (round(end.x, 5), round(end.y, 5)))))
            if key not in edge_keys:
                edge_keys.add(key)
                edges.append((start, end))
    return cells, edges


@dataclass
class VoronoiTarget:
    position: V
    radius: float = TARGET_RADIUS
    alive: bool = True
    broken_at: float | None = None
    predicted_hit: bool = False


class VoronoiMixin:
    """Siembra, frentes circulares y una descarga final sobre las bisectoras."""
    VORONOI_COLOR = (139, 246, 202)
    VORONOI_PALETTE = ((72, 235, 252), (118, 148, 255), (190, 116, 255),
                       (255, 104, 203), (255, 196, 80), (97, 246, 165),
                       (255, 145, 93))
    VORONOI_HIT_COLOR = (255, 63, 79)
    VORONOI_MARK_DURATION = 15.0
    VORONOI_GROWTH_DURATION = 2.0
    VORONOI_PULSE_DURATION = .65
    VORONOI_FADE_DURATION = .45

    def init_voronoi(self):
        self.voronoi_seeds = []
        self.voronoi_cells = []
        self.voronoi_edges = []
        self.voronoi_edge_sites = []
        self.voronoi_ghost_targets = []
        self.voronoi_collector = None
        self.voronoi_phase = None
        self.voronoi_phase_elapsed = 0.0
        self.voronoi_elapsed = 0.0
        self.voronoi_radius = 0.0
        self.voronoi_max_radius = 0.0

    def start_voronoi(self, collector=None):
        self.init_voronoi()
        self.voronoi_collector = collector if collector in self.balls else (self.balls[0] if self.balls else None)
        self.voronoi_phase = 'marking'
        # Una distribucion estratificada deja siete blancos separados incluso
        # con muchas bolas: son espectros, nunca obstaculos fisicos para ellas.
        slots = [(column, row) for row in range(3) for column in range(3)]
        for column, row in self.rng.sample(slots, 7):
            width, height = RIGHT - LEFT - 160, BOTTOM - TOP - 240
            position = V(LEFT + 80 + width * (column + self.rng.uniform(.3, .7)) / 3,
                         TOP + 80 + height * (row + self.rng.uniform(.3, .7)) / 3)
            self.voronoi_ghost_targets.append(VoronoiTarget(position))
            self.burst(position, self.VORONOI_COLOR, 7)

    def _mark_voronoi(self):
        collector = self.voronoi_collector
        if collector not in self.balls:
            collector = self.balls[0] if self.balls else None
            self.voronoi_collector = collector
        position = (V(*collector.body.position) if collector is not None else
                    (self.voronoi_seeds[-1] if self.voronoi_seeds else V((LEFT + RIGHT) / 2, (TOP + BOTTOM) / 2)))
        self.voronoi_seeds.append(position)
        self.burst(position, self.VORONOI_PALETTE[(len(self.voronoi_seeds) - 1) % len(self.VORONOI_PALETTE)], 5)

    def _form_voronoi(self):
        self.voronoi_cells, self.voronoi_edges = build_voronoi(self.voronoi_seeds)
        self.voronoi_edge_sites = [min(range(len(self.voronoi_seeds)),
                                        key=lambda index: ((start + end) * .5 - self.voronoi_seeds[index]).length_squared)
                                    for start, end in self.voronoi_edges]
        self.voronoi_max_radius = max(((vertex - site).length
                                       for site, polygon in zip(self.voronoi_seeds, self.voronoi_cells)
                                       for vertex in polygon), default=1.0)
        # The final bisectors are known before the two-second expansion starts.
        # Telegraph the exact hit test, without awarding a point until the strike.
        for target in self.voronoi_ghost_targets:
            target.predicted_hit = any(swept_circle(start, end, target.position, target.radius + 2.5)
                                       for start, end in self.voronoi_edges)
        self.voronoi_phase, self.voronoi_phase_elapsed = 'growth', 0.0
        self.message, self.message_left = 'VORONOI / CRYSTALLIZING', 2.0

    def _strike_voronoi(self):
        # Solo las aristas interiores disparan. El contorno del campo no es
        # parte de la descarga, y tocar un espectro con una bola nunca puntua.
        def intersects(position, radius):
            return any(swept_circle(start, end, position, radius + 2.5)
                       for start, end in self.voronoi_edges)

        destroyed = 0
        for target in self.voronoi_ghost_targets:
            if target.alive and intersects(target.position, target.radius):
                target.alive, target.broken_at = False, self.voronoi_elapsed
                self.score += 1
                self.hits += 1
                destroyed += 1
                self.burst(target.position, self.VORONOI_HIT_COLOR, 28)
                self.burst(target.position, (255, 216, 175), 8)
        if self.target_lock <= 0 and intersects(self.target, TARGET_RADIUS):
            self.award_target()
            destroyed += 1
        for index, site in enumerate(self.voronoi_seeds):
            self.burst(site, self.VORONOI_PALETTE[index % len(self.VORONOI_PALETTE)], 3)
        self.message = 'VORONOI / +' + str(destroyed) if destroyed else 'VORONOI / DISCHARGE'
        self.message_left = 1.5

    def step_voronoi(self, dt):
        if self.active != 'voronoi' or self.voronoi_phase is None:
            return
        remaining = max(0.0, dt)
        while remaining > 1e-10:
            phase = self.voronoi_phase
            duration = {'marking': self.VORONOI_MARK_DURATION,
                        'growth': self.VORONOI_GROWTH_DURATION,
                        'pulse': self.VORONOI_PULSE_DURATION,
                        'fade': self.VORONOI_FADE_DURATION}[phase]
            elapsed = min(remaining, max(0.0, duration - self.voronoi_phase_elapsed))
            self.voronoi_elapsed += elapsed
            self.voronoi_phase_elapsed += elapsed
            remaining -= elapsed
            if phase == 'marking':
                self.active_left = max(0.0, duration - self.voronoi_phase_elapsed)
                count = min(15, int(self.voronoi_phase_elapsed + 1e-8))
                while len(self.voronoi_seeds) < count:
                    self._mark_voronoi()
            elif phase == 'growth':
                self.voronoi_radius = self.voronoi_max_radius * clamp(self.voronoi_phase_elapsed / duration, 0, 1)
            if self.voronoi_phase_elapsed < duration - 1e-9:
                break
            if phase == 'marking':
                self._form_voronoi()
            elif phase == 'growth':
                self.voronoi_radius = self.voronoi_max_radius
                self.voronoi_phase, self.voronoi_phase_elapsed = 'pulse', 0.0
                self._strike_voronoi()
            elif phase == 'pulse':
                self.voronoi_phase, self.voronoi_phase_elapsed = 'fade', 0.0
            else:
                self.finish_powerup()
                break

    def finish_voronoi(self):
        self.init_voronoi()


class PortalTimeMixin:
    """Portales persistentes y futuros alternativos, sin cuerpos invisibles."""
    PORTAL_BLUE = (70, 170, 255)
    PORTAL_ORANGE = (255, 155, 62)
    GHOST_COLOR = (157, 231, 255)

    def init_portal_time(self):
        self.portals = []
        self.ghosts = {}
        self._portal_locks = {}

    def start_portal_time(self, kind):
        if kind == "mobius":
            self.portals.clear()
            self._portal_locks.clear()
        elif kind == "timewarp":
            self.ghosts = {ball: Ghost(ball) for ball in self.balls}
            for ghost in self.ghosts.values():
                self.update_ghost_forecast(ghost)

    def finish_portal_time(self, kind):
        if kind == "mobius":
            for portal in self.portals:
                self.burst(portal.position, portal.color, 4)
            self.portals.clear()
            self._portal_locks.clear()
        elif kind == "timewarp":
            for ghost in self.ghosts.values():
                self.burst(ghost.position, self.GHOST_COLOR, 8)
            self.ghosts.clear()
            self.projectiles[:] = [shot for shot in self.projectiles
                                   if getattr(shot, "source", None) != "timewarp"]

    @staticmethod
    def _wall_distance(position, wall):
        if wall == "left":
            return position.x - LEFT
        if wall == "right":
            return RIGHT - position.x
        if wall == "top":
            return position.y - TOP
        return BOTTOM - position.y

    def handle_portal(self, ball, start):
        if self.active != "mobius":
            return False
        position = V(*ball.body.position)
        incoming = V(*getattr(ball, "portal_incoming_velocity", ball.body.velocity))
        clearance = ball.radius + 8.0
        lock = self._portal_locks.get(ball)
        if lock and self._wall_distance(position, lock) > clearance + 3.0:
            self._portal_locks.pop(ball, None)
            lock = None
        contacts = []
        for wall, normal in (("left", V(1, 0)), ("right", V(-1, 0)),
                             ("top", V(0, 1)), ("bottom", V(0, -1))):
            if wall == lock or incoming.dot(normal) >= -1.0:
                continue
            before = self._wall_distance(start, wall) - clearance
            after = self._wall_distance(position, wall) - clearance
            if after <= 0.6 and after <= before + 0.01:
                fraction = max(0.0, min(1.0, before / (before - after))) if before > after else 0.0
                contacts.append((fraction, wall, normal))
        if not contacts:
            return False
        fraction, wall, normal = min(contacts, key=lambda item: item[0])
        contact_center = start + (position - start) * fraction
        vertical = wall in ("left", "right")
        coordinate = contact_center.y if vertical else contact_center.x
        tangent = V(0, 1) if vertical else V(1, 0)
        portal = next((item for item in self.portals if item.wall == wall
                       and abs((contact_center - item.position).dot(tangent)) <= item.half_length), None)
        if portal is None:
            half_length = max(46.0, ball.radius + 14.0)
            low, high = (TOP, BOTTOM) if vertical else (LEFT, RIGHT)
            coordinate = max(low + half_length + 8.0, min(high - half_length - 8.0, coordinate))
            anchor = V(LEFT if wall == "left" else RIGHT, coordinate) if vertical else V(coordinate, TOP if wall == "top" else BOTTOM)
            opposite = {"left": "right", "right": "left", "top": "bottom", "bottom": "top"}[wall]
            paired = V(LEFT + RIGHT - anchor.x, TOP + BOTTOM - anchor.y)
            portal = Portal(wall, anchor, paired, opposite, self.PORTAL_BLUE, True,
                            self.sim_time, half_length)
            self.portals.extend((portal, Portal(opposite, paired, anchor, wall,
                                               self.PORTAL_ORANGE, False, self.sim_time, half_length)))
            self.burst(anchor, self.PORTAL_BLUE, 10)
            self.burst(paired, self.PORTAL_ORANGE, 10)
        # La simetria central invierte la coordenada tangencial. Invertir el
        # rebote, en vez del vector que entra, hace que la salida mire al campo.
        reflected = incoming - normal * (2.0 * incoming.dot(normal))
        outgoing = -reflected
        exit_normal = -normal
        offset = (contact_center - portal.position).dot(tangent)
        destination = portal.pair_position - tangent * offset + exit_normal * (clearance + 1.2)
        destination = V(max(LEFT + clearance + 1.2, min(RIGHT - clearance - 1.2, destination.x)),
                        max(TOP + clearance + 1.2, min(BOTTOM - clearance - 1.2, destination.y)))
        ball.portal_entry_position = contact_center
        ball.body.position = destination
        ball.body.velocity = outgoing
        ball.previous = destination
        ball.trail.clear()
        self.space.reindex_shapes_for_body(ball.body)
        self._portal_locks[ball] = portal.exit_wall
        self.burst(contact_center, portal.color, 5)
        self.burst(destination, self.PORTAL_ORANGE if portal.is_entry else self.PORTAL_BLUE, 5)
        return True

    def remove_ghost_for(self, ball):
        self.ghosts.pop(ball, None)
        self._portal_locks.pop(ball, None)

    def refresh_ghost(self, ball):
        if self.active != "timewarp":
            return
        previous = self.ghosts.get(ball)
        if previous is not None:
            direction = previous.velocity.normalized() if previous.velocity.length_squared > 1e-9 else V(0, -1)
            perpendicular = V(-direction.y, direction.x)
            speed = max(700.0, min(1600.0, previous.velocity.length))
            for axis in (direction, perpendicular, -direction, -perpendicular):
                shot = Projectile(previous.position, axis * speed)
                shot.color = self.GHOST_COLOR
                shot.source = "timewarp"
                self.projectiles.append(shot)
            self.burst(previous.position, self.GHOST_COLOR, 18)
        self.ghosts[ball] = Ghost(ball)
        self.update_ghost_forecast(self.ghosts[ball])
        self.burst(ball.body.position, self.GHOST_COLOR, 8)

    def _ghost_state(self, position, velocity, radius):
        """Limites exactos y reposo estable: impide una sucesion infinita de microbotes."""
        clearance = radius + 8.0
        bounds = (LEFT + clearance, RIGHT - clearance, TOP + clearance, BOTTOM - clearance)
        position = V(max(bounds[0], min(bounds[1], position.x)),
                     max(bounds[2], min(bounds[3], position.y)))
        if velocity.length_squared > MAX_BALL_SPEED ** 2:
            velocity = velocity * (MAX_BALL_SPEED / velocity.length)
        acceleration = V(*self.space.gravity)
        values, speeds, accelerations = list(position), list(velocity), list(acceleration)
        for axis, (lower, upper) in enumerate(((bounds[0], bounds[1]), (bounds[2], bounds[3]))):
            supported = ((values[axis] <= lower + 1e-7 and accelerations[axis] < 0)
                         or (values[axis] >= upper - 1e-7 and accelerations[axis] > 0))
            if supported and abs(speeds[axis]) < 5.0:
                speeds[axis] = accelerations[axis] = 0.0
        velocity, acceleration = V(*speeds), V(*accelerations)
        # Velocidad terminal compartida por el espectro y su prevision. En el
        # tramo terminal se mantiene el vector hasta el siguiente rebote.
        if velocity.length_squared >= MAX_BALL_SPEED ** 2 - 1e-5 and velocity.dot(acceleration) >= 0:
            acceleration = V(0, 0)
        return position, velocity, acceleration, bounds

    @staticmethod
    def _ghost_roots(position, velocity, acceleration, boundary):
        if abs(acceleration) < 1e-12:
            return ((boundary - position) / velocity,) if abs(velocity) > 1e-12 else ()
        discriminant = velocity * velocity + 2.0 * acceleration * (boundary - position)
        if discriminant < 0:
            return ()
        root = math.sqrt(max(0.0, discriminant))
        return ((-velocity - root) / acceleration, (-velocity + root) / acceleration)

    def _ghost_event(self, position, velocity, radius):
        """Siguiente pared o velocidad terminal, calculadas sin pasos de simulacion."""
        position, velocity, acceleration, bounds = self._ghost_state(position, velocity, radius)
        events = []
        for axis, (lower, upper) in enumerate(((bounds[0], bounds[1]), (bounds[2], bounds[3]))):
            for boundary, direction in ((lower, -1), (upper, 1)):
                for time in self._ghost_roots(position[axis], velocity[axis], acceleration[axis], boundary):
                    if time >= -1e-8 and direction * (velocity[axis] + acceleration[axis] * max(0, time)) > 1e-8:
                        events.append((max(0.0, time), axis, boundary))
        if acceleration.length_squared > 1e-12:
            projection = velocity.dot(acceleration)
            discriminant = projection ** 2 + acceleration.length_squared * (MAX_BALL_SPEED ** 2 - velocity.length_squared)
            terminal_time = (-projection + math.sqrt(max(0.0, discriminant))) / acceleration.length_squared
            if terminal_time > 1e-8:
                events.append((terminal_time, None, None))
        event_time = min((item[0] for item in events), default=math.inf)
        walls = [(axis, boundary) for time, axis, boundary in events
                 if axis is not None and abs(time - event_time) <= 1e-8]
        return position, velocity, acceleration, event_time, walls

    @staticmethod
    def _ghost_curve(position, velocity, acceleration, duration):
        """Polilinea de error inferior a 0,18 px; los tramos fisicos siguen siendo parabolas."""
        deviation_steps = math.ceil(math.sqrt(acceleration.length * duration ** 2 / 1.44))
        distance = velocity.length * duration + 0.5 * acceleration.length * duration ** 2
        steps = max(1, deviation_steps, math.ceil(distance / 64.0))
        return [(duration * index / steps,
                 position + velocity * (duration * index / steps)
                 + acceleration * (0.5 * (duration * index / steps) ** 2))
                for index in range(1, steps + 1)]

    @staticmethod
    def _ghost_target_contact(start, end, target, radius):
        delta, offset = end - start, start - target
        if offset.length_squared <= radius ** 2:
            return 0.0, start
        if delta.length_squared < 1e-15:
            return None
        projection = offset.dot(delta)
        discriminant = projection ** 2 - delta.length_squared * (offset.length_squared - radius ** 2)
        if discriminant < 0:
            return None
        fraction = (-projection - math.sqrt(discriminant)) / delta.length_squared
        return (fraction, start + delta * fraction) if 0 <= fraction <= 1 else None

    def _advance_ghost(self, ghost, dt):
        """La trayectoria y el anticipo usan exactamente los mismos eventos balisticos."""
        remaining, hit = dt, False
        # Una alteracion externa del estado invalida tambien una ruta previamente calculada.
        if ghost._forecast_state != (ghost.position, ghost.velocity):
            ghost._forecast_key = None
        while remaining > 1e-10:
            start, velocity, acceleration, event_time, walls = self._ghost_event(
                ghost.position, ghost.velocity, ghost.radius)
            duration = min(remaining, event_time)
            previous = start
            for _, point in self._ghost_curve(start, velocity, acceleration, duration):
                if self.target_lock <= 0 and swept_circle(previous, point, self.target, ghost.radius + TARGET_RADIUS):
                    hit = True
                previous = point
            ghost.position = start + velocity * duration + acceleration * (0.5 * duration ** 2)
            ghost.velocity = velocity + acceleration * duration
            sample = 1.0 / 120.0 - ghost.trail_clock
            while sample <= duration + 1e-10:
                ghost.trail.append(start + velocity * sample + acceleration * (0.5 * sample ** 2))
                sample += 1.0 / 120.0
            ghost.trail_clock = (ghost.trail_clock + duration) % (1.0 / 120.0)
            ghost.motion_time += duration
            remaining -= duration
            if event_time <= duration + 1e-9:
                coordinates, speeds = list(ghost.position), list(ghost.velocity)
                for axis, boundary in walls:
                    coordinates[axis] = boundary
                    speeds[axis] *= -ghost.restitution
                ghost.position, ghost.velocity = V(*coordinates), V(*speeds)
                if walls:
                    ghost.wall_collisions += 1
            else:
                break
        ghost._forecast_state = (ghost.position, ghost.velocity)
        return hit

    def update_ghost_forecast(self, ghost):
        """Diez rebotes futuros; recalcula solo al rebotar o cambiar la fisica."""
        key = (tuple(self.space.gravity), ghost.radius, ghost.restitution, ghost.wall_collisions)
        if ghost._forecast_key != key:
            position, velocity = ghost.position, ghost.velocity
            time = ghost.motion_time
            records, bounces = [(time, position)], []
            # Como maximo hay un tramo terminal adicional por rebote. El limite
            # de eventos es de trabajo, no recorta los diez rebotes normales.
            for _ in range(32):
                start, velocity, acceleration, duration, walls = self._ghost_event(position, velocity, ghost.radius)
                if not math.isfinite(duration):
                    break
                for offset, point in self._ghost_curve(start, velocity, acceleration, duration):
                    records.append((time + offset, point))
                position = start + velocity * duration + acceleration * (0.5 * duration ** 2)
                velocity += acceleration * duration
                time += duration
                coordinates, speeds = list(position), list(velocity)
                for axis, boundary in walls:
                    coordinates[axis] = boundary
                    speeds[axis] *= -ghost.restitution
                position, velocity = V(*coordinates), V(*speeds)
                if walls:
                    bounces.append((time, position))
                    if len(bounces) == 10:
                        break
            ghost._forecast_records = records
            ghost._forecast_bounces = bounces
            ghost._forecast_key = key
            ghost._forecast_target = None
            ghost.forecast_revision += 1
        future = [(time, point) for time, point in ghost._forecast_records
                  if time > ghost.motion_time + 1e-9]
        ghost.forecast_points = [ghost.position] + [point for _, point in future]
        ghost.forecast_impacts = [point for time, point in ghost._forecast_bounces
                                 if time > ghost.motion_time + 1e-9]
        target_key = tuple(self.target)
        if (ghost._forecast_target != target_key
                or (ghost._forecast_hit_time is not None and ghost._forecast_hit_time < ghost.motion_time)):
            ghost._forecast_hit_position = None
            ghost._forecast_hit_time = None
            previous_time, previous = ghost.motion_time, ghost.position
            for time, point in future:
                contact = self._ghost_target_contact(previous, point, self.target, ghost.radius + TARGET_RADIUS)
                if contact is not None:
                    fraction, ghost._forecast_hit_position = contact
                    ghost._forecast_hit_time = previous_time + (time - previous_time) * fraction
                    break
                previous_time, previous = time, point
            ghost._forecast_target = target_key
        # Los diez rebotes permanecen visibles, pero solo se anuncia un acierto
        # si el espectro puede alcanzarlo antes de que termine el powerup.
        expires_at = ghost.motion_time + 3.0 * max(0.0, self.active_left)
        ghost.forecast_hit_pos = (ghost._forecast_hit_position
                                  if ghost._forecast_hit_time is not None
                                  and ghost._forecast_hit_time <= expires_at + 1e-9 else None)
        ghost._forecast_state = (ghost.position, ghost.velocity)

    def step_ghosts(self, dt):
        if self.active != "timewarp":
            return False
        live_balls = set(self.balls)
        for ball in tuple(self.ghosts):
            if ball not in live_balls:
                self.ghosts.pop(ball)
        for ball in self.balls:
            if ball not in self.ghosts:
                self.ghosts[ball] = Ghost(ball)
        hit = False
        for ghost in self.ghosts.values():
            ghost.previous = ghost.position
            ghost.age += dt
            ghost.phase += dt * 3.0
            hit |= self._advance_ghost(ghost, dt * 3.0)
            self.update_ghost_forecast(ghost)
        return hit


WORMHOLE_ENTRY_RADIUS = 44.0
WORMHOLE_BUILD_DURATION = .7
WORMHOLE_TERMINAL_SPEED = 900.0
WORMHOLE_COLOR = (119, 153, 255)


@dataclass
class WormholeRoute:
    """Curva muestreada por longitud de arco: rapidez real independiente del dibujo."""
    points: tuple
    cumulative: tuple
    length: float
    target: V

    def point_at(self, distance):
        distance = clamp(distance, 0.0, self.length)
        lo, hi = 1, len(self.cumulative) - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.cumulative[mid] < distance:
                lo = mid + 1
            else:
                hi = mid
        index = lo
        delta = self.points[index] - self.points[index - 1]
        segment_length = self.cumulative[index] - self.cumulative[index - 1]
        fraction = (distance - self.cumulative[index - 1]) / max(segment_length, 1e-9)
        tangent = delta.normalized() if delta.length_squared > 1e-12 else V(0, -1)
        return self.points[index - 1] + delta * fraction, tangent


@dataclass
class WormholeTransit:
    route: WormholeRoute
    distance: float
    speed: float
    age: float = 0.0


class WormholeMixin:
    """La boca captura; el resto del tejido es una guia sin colisiones propias."""
    def init_wormhole(self):
        self.wormhole_entry = None
        self.wormhole_route = None
        self.wormhole_build = 0.0
        self.wormhole_close_left = 0.0
        self.wormhole_transits = {}
        self.wormhole_generation = 0

    def make_wormhole_route(self, start, target, bend=None):
        start, target = V(*start), V(*target)
        delta = target - start
        length = delta.length
        along = delta / length if length > 1e-9 else V(0, -1)
        normal = V(-along.y, along.x)
        if bend is None:
            bend = self.rng.choice((-1, 1)) * min(190.0, max(45.0, length * .27))
        # La envolvente convexa de Bezier mantiene el tubo dentro del campo.
        def inset(point):
            return V(clamp(point.x, LEFT + 52, RIGHT - 52),
                     clamp(point.y, TOP + 52, BOTTOM - 100))
        a = inset(start + delta * .30 + normal * bend)
        b = inset(target - delta * .28 - normal * bend * .55)
        points = []
        for i in range(97):
            t = i / 96
            s = 1 - t
            points.append(start * s ** 3 + a * (3 * s * s * t)
                          + b * (3 * s * t * t) + target * t ** 3)
        distances = [0.0]
        for p, q in zip(points, points[1:]):
            distances.append(distances[-1] + (q - p).length)
        return WormholeRoute(tuple(points), tuple(distances), distances[-1], target)

    def start_wormhole(self):
        self.wormhole_transits.clear()
        self.wormhole_close_left = 0.0
        middle = (TOP + BOTTOM) * .5
        # Evitar la pala y una salida inmediata encima del objetivo inicial.
        candidates = [V(self.rng.uniform(LEFT + 110, RIGHT - 110),
                        self.rng.uniform(middle + 52, BOTTOM - 165)) for _ in range(48)]
        self.wormhole_entry = next((p for p in candidates
                                   if self.safe_position(p, WORMHOLE_ENTRY_RADIUS + 15,
                                                         avoid_target=True)), candidates[0])
        self.on_target_changed_wormhole()
        self.burst(self.wormhole_entry, WORMHOLE_COLOR, 30)

    def on_target_changed_wormhole(self):
        if self.active != 'wormhole' or self.wormhole_entry is None:
            return
        self.wormhole_generation += 1
        self.wormhole_route = self.make_wormhole_route(self.wormhole_entry, self.target)
        self.wormhole_build = 0.0
        # Reencaminar desde la posicion ACTUAL, nunca desde la nueva boca.
        # Cada pasajero conserva un ramal continuo hasta la nueva salida.
        for ball, transit in self.wormhole_transits.items():
            transit.route = self.make_wormhole_route(ball.body.position, self.target)
            transit.distance = 0.0
            transit.age = 0.0

    def capture_wormhole(self, ball, start, end):
        if (self.active != 'wormhole' or self.wormhole_entry is None
                or self.wormhole_route is None or ball in self.wormhole_transits
                or ball.body.space is not self.space
                or self.sim_time < getattr(ball, 'wormhole_ready_at', 0.0)):
            return False
        if not swept_circle(start, end, self.wormhole_entry,
                            WORMHOLE_ENTRY_RADIUS + ball.radius):
            return False
        # El primer tramo une el punto de captura con el centro de la boca,
        # sin el salto de posicion que produciria un teletransporte al centro.
        route = self.wormhole_route
        position = V(*end)
        points = (position,) + route.points
        lead = (position - route.points[0]).length
        distances = (0.0,) + tuple(lead + d for d in route.cumulative)
        passenger_route = WormholeRoute(points, distances, lead + route.length, route.target)
        speed = clamp(ball.body.velocity.length, 120.0, MAX_BALL_SPEED)
        self.wormhole_transits[ball] = WormholeTransit(passenger_route, 0.0, speed)
        ball.wormhole_transit = True
        self.space.remove(ball.shape, ball.body)
        self.by_body.pop(ball.body, None)
        self.paddle_impacts.discard(ball)
        self.wall_impacts.discard(ball)
        self.wave_contacts.pop(ball, None)
        self.burst(position, WORMHOLE_COLOR, 10)
        return True

    def release_wormhole_ball(self, ball, transit):
        self.wormhole_transits.pop(ball, None)
        ball.wormhole_transit = False
        if ball not in self.balls:
            return
        position, tangent = transit.route.point_at(transit.distance)
        # Solo separar de superficies locales si la pala ha pasado por el tubo.
        ball.body.position = self.fit_to_solids(position, ball.radius)
        ball.body.velocity = tangent * min(transit.speed, MAX_BALL_SPEED)
        ball.previous = V(*ball.body.position)
        ball.wormhole_ready_at = self.sim_time + .35
        if ball.body.space is not self.space:
            self.space.add(ball.body, ball.shape)
        self.by_body[ball.body] = ball
        ball.body.activate()
        self.burst(ball.body.position, WORMHOLE_COLOR, 12)

    def step_wormhole(self, dt):
        if self.active != 'wormhole':
            if self.wormhole_close_left > 0:
                self.wormhole_close_left = max(0.0, self.wormhole_close_left - dt)
                if self.wormhole_close_left <= 0:
                    self.wormhole_entry = None
                    self.wormhole_route = None
                    self.wormhole_build = 0.0
            return
        if self.wormhole_route is None:
            return
        if (self.wormhole_route.target - self.target).length_squared > 1e-9:
            self.on_target_changed_wormhole()
        self.wormhole_build = min(1.0, self.wormhole_build + dt / WORMHOLE_BUILD_DURATION)
        for ball, transit in tuple(self.wormhole_transits.items()):
            if ball not in self.balls:
                self.wormhole_transits.pop(ball, None)
                continue
            transit.age += dt
            transit.speed = (WORMHOLE_TERMINAL_SPEED
                             + (transit.speed - WORMHOLE_TERMINAL_SPEED) * math.exp(-3.5 * dt))
            travel = transit.speed * dt
            # Una bola no adelanta al frente que esta tejiendo su tunel.
            available = transit.route.length * self.wormhole_build
            transit.distance = min(available, transit.route.length, transit.distance + travel)
            position, tangent = transit.route.point_at(transit.distance)
            ball.body.position = position
            ball.body.velocity = tangent * transit.speed
            if transit.distance >= transit.route.length - 1e-6 and self.target_lock <= 0:
                # Salir fisicamente sobre el objetivo y puntuar una unica vez.
                # El cambio de objetivo actualiza los pasajeros restantes.
                self.release_wormhole_ball(ball, transit)
                self.award_target(ball)

    def finish_wormhole(self):
        for ball, transit in tuple(self.wormhole_transits.items()):
            self.release_wormhole_ball(ball, transit)
        self.wormhole_close_left = .35
        if self.wormhole_entry is not None:
            self.burst(self.wormhole_entry, WORMHOLE_COLOR, 28)


@dataclass
class SnellBranches:
    reflected: V
    refracted: V | None
    reflectance: float
    total_internal: bool


@dataclass
class SnellFlash:
    position: V
    reflected: bool
    total_internal: bool
    age: float = 0.0


def snell_branches(velocity, from_upper, upper_index=1.45, lower_index=1.0):
    """Ramas opticas y Fresnel no polarizado para una interfaz horizontal.

    La velocidad cambia como 1/n. El limite de seguridad escala el vector
    transmitido entero y conserva su angulo de Snell.
    """
    incoming = V(*velocity)
    speed = incoming.length
    reflected = V(incoming.x, -incoming.y)
    if speed < 1e-9:
        return SnellBranches(reflected, V(0, 0), 0.0, False)
    n1, n2 = (upper_index, lower_index) if from_upper else (lower_index, upper_index)
    ratio = n1 / n2
    sin_incident = clamp(incoming.x / speed, -1.0, 1.0)
    sin_transmitted = ratio * sin_incident
    if abs(sin_transmitted) >= 1.0:
        return SnellBranches(reflected, None, 1.0, True)
    cos_incident = abs(incoming.y) / speed
    cos_transmitted = math.sqrt(max(0.0, 1.0 - sin_transmitted ** 2))
    rs = ((n1 * cos_incident - n2 * cos_transmitted)
          / max(1e-12, n1 * cos_incident + n2 * cos_transmitted)) ** 2
    rp = ((n1 * cos_transmitted - n2 * cos_incident)
          / max(1e-12, n1 * cos_transmitted + n2 * cos_incident)) ** 2
    transmitted_speed = min(MAX_BALL_SPEED, speed * ratio)
    normal_sign = 1.0 if from_upper else -1.0
    refracted = V(sin_transmitted, normal_sign * cos_transmitted) * transmitted_speed
    return SnellBranches(reflected, refracted, clamp((rs + rp) * .5, 0.0, 1.0), False)


class SnellMixin:
    """Dos medios, una interfaz y una rama luminosa complementaria por cruce."""
    def init_snell(self):
        self.snell_line_y = (TOP + BOTTOM) * .5
        self.snell_targets = []
        self.snell_flashes = []
        self.snell_saved_target = None

    def _snell_target_position(self, index):
        margin = TARGET_RADIUS + 34.0
        low = TOP + margin if index == 0 else self.snell_line_y + margin
        high = self.snell_line_y - margin if index == 0 else BOTTOM - 135.0
        for _ in range(80):
            pos = V(self.rng.uniform(LEFT + margin, RIGHT - margin), self.rng.uniform(low, high))
            if self.safe_position(pos, TARGET_RADIUS + 8):
                return pos
        # Incluso con el easter egg saturando la pantalla deben existir dos
        # objetivos. Si no hay hueco libre, escoger el lugar menos ocupado.
        candidates = [V(LEFT + margin + (RIGHT - LEFT - 2 * margin) * x / 10,
                        low + (high - low) * y / 5)
                      for y in range(6) for x in range(11)]
        return max(candidates, key=lambda p: min(
            [(p - ball.body.position).length - ball.radius for ball in self.balls] or [9999]))

    def start_snell(self):
        self.snell_saved_target = V(*self.target)
        self.snell_targets = [self._snell_target_position(0), self._snell_target_position(1)]
        self.target = self.snell_targets[0]
        self.snell_flashes.clear()
        self.target_lock = .08
        for ball in self.balls:
            ball.snell_crossings = 0
            ball.snell_last_branch = None
        for target in self.snell_targets:
            self.burst(target, (172, 223, 255), 18)

    def replace_snell_target(self, index):
        if not 0 <= index < len(self.snell_targets):
            return None
        self.snell_targets[index] = self._snell_target_position(index)
        self.target = self.snell_targets[0]
        return self.snell_targets[index]

    def finish_snell(self):
        self.snell_targets.clear()
        self.snell_flashes.clear()
        self.projectiles = [shot for shot in self.projectiles if getattr(shot, 'source', None) != 'snell']
        for ball in self.balls:
            ball.snell_last_branch = None
        self.snell_saved_target = None

    def step_snell(self, dt):
        for flash in self.snell_flashes:
            flash.age += dt
        self.snell_flashes = [flash for flash in self.snell_flashes if flash.age < .65]

    def handle_snell(self, ball, start, dt):
        """Barrido del centro visible, sin teletransportarlo a traves del diametro.

        Devuelve los dos tramos reales recorridos para sensores de objetivos.
        Al reflejar, el tiempo restante del subpaso se recorre hacia el medio
        de entrada; por ello no vuelve a dispararse al siguiente fotograma.
        """
        if self.active != 'snell' or dt <= 0:
            return None
        start, end = V(*start), V(*ball.body.position)
        before, after = start.y - self.snell_line_y, end.y - self.snell_line_y
        dy = end.y - start.y
        if abs(dy) < 1e-10:
            return None
        # El extremo final puede caer exactamente sobre la interfaz. Se trata
        # ahora y se separa una tolerancia minima en el lado de salida.
        if not ((before < 0 <= after) or (before > 0 >= after)):
            return None
        fraction = clamp(-before / dy, 0.0, 1.0)
        contact = start + (end - start) * fraction
        contact = V(contact.x, self.snell_line_y)
        from_upper = before < 0
        # La integracion ya aplico gravedad y otras colisiones del subpaso.
        incoming = V(*ball.body.velocity)
        if incoming.y * dy <= 0:
            return None
        branches = snell_branches(incoming, from_upper)
        reflected = branches.total_internal or self.rng.random() < branches.reflectance
        outgoing = branches.reflected if reflected else branches.refracted
        refracted_ray = branches.refracted
        if refracted_ray is None:
            # En reflexion total no existe un rayo refractado real. La licencia
            # arcade es un pulso evanescente casi rasante en el segundo medio.
            tangent_sign = -1.0 if incoming.x < 0 else 1.0
            refracted_ray = V(tangent_sign, .12 if from_upper else -.12).normalized()
        shot_speed = clamp(incoming.length * 1.25, 950.0, 1500.0)
        # Ambas ramas son visibles en cada impacto. Se conserva exactamente
        # la eleccion Fresnel de la pelota; los rayos son sensores independientes.
        rays = ((branches.reflected, 'reflection'), (refracted_ray, 'refraction'))
        for direction, branch in rays:
            if direction.length_squared <= 1e-12:
                continue
            shot = Projectile(contact, direction.normalized() * shot_speed, (216, 238, 255))
            shot.rainbow, shot.source = True, 'snell'
            shot.snell_branch = branch
            shot.evanescent = branch == 'refraction' and branches.total_internal
            shot.trail = deque([contact], maxlen=72)
            self.projectiles.append(shot)
        remaining = dt * (1.0 - fraction)
        final = contact + outgoing * remaining
        outgoing_side = -1 if (from_upper == reflected) else 1
        if abs(final.y - self.snell_line_y) < 1e-5:
            final = V(final.x, self.snell_line_y + outgoing_side * 1e-5)
        ball.body.position, ball.body.velocity = final, outgoing
        ball.body.activate()
        self.space.reindex_shapes_for_body(ball.body)
        ball.snell_crossings = getattr(ball, 'snell_crossings', 0) + 1
        ball.snell_last_branch = 'reflection' if reflected else 'refraction'
        self.snell_flashes.append(SnellFlash(contact, reflected, branches.total_internal))
        self.snell_flashes = self.snell_flashes[-40:]
        for color in ((255, 92, 171), (104, 236, 255), (255, 221, 112)):
            self.burst(contact, color, 5)
        return [(start, contact), (contact, final)]


QUANTUM_COLORS = {1: (255, 78, 104), -1: (74, 162, 255)}
QUANTUM_BOLT_LIFETIME = .19
QUANTUM_MIN_APPROACH = 6.0


@dataclass
class QuantumBolt:
    points: tuple
    color: tuple
    age: float = 0.0


class QuantumMixin:
    """Transfer paddle impulses once; gravity and arena contacts stay local."""

    def init_quantum(self):
        self.quantum_pair = None
        self.quantum_unobserved = None
        self.quantum_real = None
        self.quantum_waiting = None
        self.quantum_retry_at = 0.0
        self.quantum_bolts = []
        self.quantum_impulses = []
        self.quantum_approaches = {}
        self.quantum_observations = []

    def start_quantum(self, collector=None):
        if not self.balls:
            return
        # Normal flow cannot collect another powerup until observation. This
        # guard also makes forced previews/diagnostic activation well-defined.
        if self.quantum_unobserved:
            self.collapse_quantum()
        self.quantum_waiting = collector if collector in self.balls else self.balls[0]
        self.quantum_retry_at = self.sim_time
        self._spawn_quantum_pair()

    def _spawn_quantum_pair(self):
        original = self.quantum_waiting
        if original not in self.balls or self.quantum_pair is not None:
            self.quantum_waiting = None
            return
        radius, origin = original.radius, V(*original.body.position)
        velocity = V(*original.body.velocity)
        direction = velocity.normalized() if velocity.length_squared > 1 else V(0, -1)
        side = V(-direction.y, direction.x)
        chosen = None
        # Search around the collector first, without moving it or allowing the
        # pair to overlap. A crowded field may delay birth until space is free.
        for offset in (0, 1, -1, 2, -2, 3, -3, 4):
            candidate = self.fit_to_solids(origin + side.rotated(offset * math.pi / 4)
                                           * (2 * radius + 5), radius)
            if self.safe_position(candidate, radius):
                chosen = candidate
                break
        if chosen is None:
            chosen = self.free_position(radius)
        if chosen is None:
            self.quantum_retry_at = self.sim_time + .10
            return
        # Both electrons keep the original physical mass, radius and gravity.
        # Independent launch headings break symmetry before the first paddle hit.
        twin = Ball(self.space, chosen, velocity, radius, temporary=original.temporary)
        twin.body.mass = original.body.mass
        twin.body.moment = pymunk.moment_for_circle(twin.body.mass, 0, radius)
        self.balls.append(twin)
        self.by_body[twin.body] = twin
        original.quantum_charge, twin.quantum_charge = 1, -1
        original.trail.clear()
        self.quantum_pair = (original, twin)
        self.scatter_quantum_pair(self.quantum_pair)
        self.quantum_waiting = None
        self.burst(original.body.position, QUANTUM_COLORS[1], 14)
        self.burst(twin.body.position, QUANTUM_COLORS[-1], 14)

    def scatter_quantum_pair(self, pair):
        a, b = pair
        separation = b.body.position - a.body.position
        axis = separation.normalized() if separation.length_squared > 1e-8 else V(1, 0)
        base_speed = clamp((a.body.velocity.length + b.body.velocity.length) * .5, 360, 850)
        for ball, direction in ((a, -axis), (b, axis)):
            heading = direction.rotated(self.rng.uniform(-.48, .48))
            ball.body.velocity = heading * base_speed * self.rng.uniform(.88, 1.12)
            ball.limit_speed(self.speed_limit)
            ball.trail.clear()

    def finish_quantum(self):
        self.quantum_waiting = None
        self.quantum_impulses.clear()
        self.quantum_approaches.clear()
        pair = self.quantum_pair
        self.quantum_pair = None
        if pair is None:
            return
        survivors = tuple(ball for ball in pair if ball in self.balls)
        for ball in survivors:
            ball.quantum_charge = 0
            ball.trail.clear()
            self.burst(ball.body.position, (201, 219, 245), 10)
        if len(survivors) == 2:
            self.scatter_quantum_pair(survivors)
            self.quantum_unobserved = survivors
            self.quantum_real = survivors[self.rng.getrandbits(1)]

    @staticmethod
    def _quantum_contact(arbiter):
        for index, shape in enumerate(arbiter.shapes):
            other = arbiter.shapes[1 - index]
            if shape.collision_type == 1 and other.collision_type == 3:
                return index, shape, other
        return None

    def record_quantum_pre(self, arbiter):
        contact = self._quantum_contact(arbiter)
        if contact is None:
            return
        index, shape, other = contact
        ball = self.by_body.get(shape.body)
        if ball is None:
            return
        if self.quantum_unobserved and ball in self.quantum_unobserved and other.collision_type == 3:
            # Touching either branch observes the system, even a gentle catch.
            self.quantum_observations.append(ball)
        if self.active != 'quantum' or not self.quantum_pair or ball not in self.quantum_pair:
            return
        normal = arbiter.normal * (1 if index == 0 else -1)
        surface_velocity = other.body.velocity_at_world_point(ball.body.position)
        approach = (ball.body.velocity - surface_velocity).dot(normal)
        self.quantum_approaches[(ball, other)] = approach

    def record_quantum_post(self, arbiter):
        contact = self._quantum_contact(arbiter)
        if contact is None or self.active != 'quantum' or self.quantum_pair is None:
            return
        index, shape, other = contact
        ball = self.by_body.get(shape.body)
        if ball not in self.quantum_pair:
            return
        approach = self.quantum_approaches.pop((ball, other), 0.0)
        # A resting constraint cancels gravity each frame, but is not a bounce.
        # Excluding it avoids silently transmitting gravity through the floor.
        if approach < QUANTUM_MIN_APPROACH:
            return
        impulse = arbiter.total_impulse * (1 if index == 0 else -1)
        if impulse.length_squared > .01:
            self.quantum_impulses.append((ball, V(*impulse)))

    def apply_quantum_impulses(self, hit_targets):
        pending, self.quantum_impulses = self.quantum_impulses, []
        self.quantum_approaches.clear()
        if self.active != 'quantum' or self.quantum_pair is None:
            return
        pair = self.quantum_pair
        accumulated = {}
        for source, impulse in pending:
            if source not in pair or any(ball not in self.balls for ball in pair):
                continue
            receiver = pair[1] if source is pair[0] else pair[0]
            accumulated[receiver] = accumulated.get(receiver, V(0, 0)) - impulse
            self._quantum_flash(source, receiver, hit_targets)
        # Accumulate before capping so simultaneous impacts are independent of
        # callback ordering. Applying impulse preserves the receiver's momentum.
        for receiver, impulse in accumulated.items():
            receiver.body.apply_impulse_at_world_point(impulse, receiver.body.position)
            receiver.limit_speed(self.speed_limit)

    def _quantum_flash(self, source, receiver, hit_targets):
        start, end = V(*source.body.position), V(*receiver.body.position)
        delta = end - start
        length = delta.length
        normal = V(-delta.y, delta.x) / length if length > 1e-9 else V(0, 1)
        segments = max(2, min(64, math.ceil(length / 28)))
        amplitude = min(13.0, length * .026)
        # Geometry uses deterministic trigonometry, never gameplay RNG and
        # never an effects-only random sequence: collision stays identical with
        # visual particles disabled and across rendering rates.
        phase = self.sim_time * 37.0 + source.quantum_charge * 2.1
        points = [start]
        for index in range(1, segments):
            amount = index / segments
            wave = math.sin(index * 12.9898 + phase) * math.sin(math.pi * amount)
            points.append(start + delta * amount + normal * (amplitude * wave))
        points.append(end)
        color = QUANTUM_COLORS[receiver.quantum_charge]
        self.quantum_bolts.append(QuantumBolt(tuple(points), color))
        # Capping only fading artwork never limits physical events or scoring.
        self.quantum_bolts = self.quantum_bolts[-36:]
        for target_index, target in self.active_targets():
            if (target_index not in hit_targets and self.target_ready(target_index)
                    and any(swept_circle(a, b, target, TARGET_RADIUS + 2.8)
                            for a, b in zip(points, points[1:]))):
                hit_targets[target_index] = receiver

    def tick_quantum(self, dt):
        for bolt in self.quantum_bolts:
            bolt.age += dt
        self.quantum_bolts = [bolt for bolt in self.quantum_bolts if bolt.age < QUANTUM_BOLT_LIFETIME]
        if (self.active == 'quantum' and self.quantum_waiting is not None
                and self.sim_time >= self.quantum_retry_at):
            self._spawn_quantum_pair()

    def resolve_quantum_observations(self):
        observations, self.quantum_observations = self.quantum_observations, []
        if self.quantum_unobserved and any(ball in self.quantum_unobserved for ball in observations):
            self.collapse_quantum()

    def collapse_quantum(self):
        pair = self.quantum_unobserved
        if pair is None:
            return
        real = self.quantum_real
        self.quantum_unobserved, self.quantum_real = None, None
        self.quantum_observations.clear()
        for ball in pair:
            if ball is not real and ball in self.balls:
                self.burst(ball.body.position, (192, 208, 244), 30)
                self.remove_ball(ball)
        if real in self.balls:
            real.quantum_charge = 0
            self.burst(real.body.position, (226, 238, 255), 12)
        self.message, self.message_left = 'WAVEFUNCTION COLLAPSED', 1.8

    def remove_quantum_ball(self, ball):
        """Called before ordinary removal: detach references, never remove twice."""
        if ball is self.quantum_waiting:
            self.quantum_waiting = None
        if self.quantum_pair and ball in self.quantum_pair:
            for other in self.quantum_pair:
                other.quantum_charge = 0
            self.quantum_pair = None
            self.quantum_impulses.clear()
        if self.quantum_unobserved and ball in self.quantum_unobserved:
            self.quantum_unobserved, self.quantum_real = None, None
        self.quantum_observations = [candidate for candidate in self.quantum_observations if candidate is not ball]


class QuantumRendererMixin:
    def draw_quantum(self, world):
        for bolt in world.quantum_bolts:
            ratio = max(0.0, 1 - bolt.age / QUANTUM_BOLT_LIFETIME)
            points = [self.project(point) for point in bolt.points]
            pygame.draw.lines(self.canvas, self.shade(bolt.color, ratio * .15), False, points, 11)
            pygame.draw.lines(self.canvas, self.shade(bolt.color, ratio * .52), False, points, 4)
            pygame.draw.aalines(self.canvas, self.shade(bolt.color, ratio), False, points)
            if ratio > .62:
                pygame.draw.aalines(self.canvas, self.shade(INK, ratio), False, points)
            for endpoint in (points[0], points[-1]):
                self.halo(endpoint, bolt.color, 22)

    def draw_quantum_electron(self, world, ball, position, radius):
        charge = getattr(ball, 'quantum_charge', 0)
        if not charge:
            return
        color = QUANTUM_COLORS[charge]
        self.halo(position, color, max(18, int(radius * 2.8)))
        phase = world.sim_time * (6.0 if charge > 0 else -6.0)
        for orbit in range(2):
            angle = phase + orbit * math.pi
            nodes = [position + V(math.cos(angle + j * .13), math.sin(angle + j * .13))
                     * (radius + 4 + math.sin(j * 1.7 + phase) * 1.4) for j in range(9)]
            pygame.draw.aalines(self.canvas, color, False, nodes)
            pygame.draw.circle(self.canvas, INK, nodes[-1], 2)
        # Dark, crisp polarity is legible even when the color is saturated.
        arm = max(3, round(radius * .42))
        pygame.draw.line(self.canvas, BG, position - V(arm, 0), position + V(arm, 0), 2)
        if charge > 0:
            pygame.draw.line(self.canvas, BG, position - V(0, arm), position + V(0, arm), 2)


GAUSSIAN_PRIZES = (32, 16, 8, 4, 2, 0, 2, 4, 8, 16, 32)
GAUSSIAN_ROWS = 10
GAUSSIAN_AIM_TIME = 5.0
GAUSSIAN_BALL_RADIUS = 6.5
GAUSSIAN_PIN_RADIUS = 11.0
GAUSSIAN_PIN_SPACING = 54.0
GAUSSIAN_ROW_HEIGHT = 24.0
GAUSSIAN_HOP_TIME = .28
GAUSSIAN_EXIT_TIME = .48
GAUSSIAN_HOP_HEIGHT = 14.0
GAUSSIAN_MAX_FALL_TIME = 24.0
GAUSSIAN_FADE_TIME = .7
GAUSSIAN_TEAL = (82, 236, 213)
GAUSSIAN_AMBER = (255, 196, 97)
GAUSSIAN_SOLID_TYPE = 64
GAUSSIAN_PIN_TYPE = 65


class GaussianMixin:
    """A live arena: physical funnel, then ten independent fair peg bounces.

    Only the collector becomes a kinematic sensor while following the pegs.
    It remains in the main space, so ordinary swept target scoring keeps using
    its actual visible path; the paddle and every other ball keep simulating.
    """
    def init_gaussian(self):
        self.gaussian_phase = None
        self.gaussian_collector = None
        self.gaussian_elapsed = 0.0
        self.gaussian_phase_elapsed = 0.0
        self.gaussian_row = 0
        self.gaussian_bin = None
        self.gaussian_prize = 0
        self.gaussian_paid = False
        self.gaussian_runs = 0
        self.gaussian_counts = [0] * 11
        self.gaussian_last_result = None
        self.gaussian_position = self.gaussian_aim_position()
        self.gaussian_previous = self.gaussian_position
        self.gaussian_pin_pulses = []
        self.gaussian_trace = deque(maxlen=220)
        self.gaussian_trace_clock = 0.0
        self.gaussian_fade_left = 0.0
        self.gaussian_shapes = []
        self.gaussian_pin_shapes = {}
        self.gaussian_segments = []
        self.gaussian_contact_rows = set()
        self.gaussian_original = None
        self.gaussian_capture_pending = False
        self.gaussian_column = 0
        self.gaussian_bits = []
        self.gaussian_hop_elapsed = 0.0
        self.gaussian_hop_start = self.gaussian_position
        self.gaussian_hop_end = self.gaussian_position
        self.gaussian_route_done = False
        self.space.on_collision(1, GAUSSIAN_SOLID_TYPE, pre_solve=self._gaussian_solid_pre)
        self.space.on_collision(1, GAUSSIAN_PIN_TYPE, pre_solve=self._gaussian_pin_pre)

    @staticmethod
    def gaussian_pin(row, column):
        return V((LEFT + RIGHT) * .5 + (column - row * .5) * GAUSSIAN_PIN_SPACING,
                 TOP + 171 + row * GAUSSIAN_ROW_HEIGHT)

    @staticmethod
    def gaussian_bin_position(index):
        return V((LEFT + RIGHT) * .5 + (index - 5) * GAUSSIAN_PIN_SPACING,
                 TOP + 171 + (GAUSSIAN_ROWS - 1) * GAUSSIAN_ROW_HEIGHT + 80)

    def gaussian_aim_position(self):
        center = (LEFT + RIGHT) * .5
        fraction = clamp((self.paddle.position.x - center) / ((RIGHT - LEFT) * .38), -1, 1)
        return V(center + fraction * 97, TOP + 58)

    def _gaussian_segment(self, start, end, radius=2.0):
        shape = pymunk.Segment(self.space.static_body, start, end, radius)
        shape.collision_type = GAUSSIAN_SOLID_TYPE
        shape.elasticity, shape.friction = .08, .02
        self.space.add(shape)
        self.gaussian_shapes.append(shape)
        self.gaussian_segments.append((V(*start), V(*end), 'rail'))
        return shape

    def _build_gaussian_board(self):
        center = (LEFT + RIGHT) * .5
        first = self.gaussian_pin(0, 0)
        last = self.gaussian_pin(9, 0)
        bottom = self.gaussian_bin_position(0).y + 9
        half = GAUSSIAN_PIN_SPACING * 5.5
        # Slim funnel, closed at the top: even an upward deflection stays inside.
        mouth_y, neck_y = TOP + 42, first.y - 33
        self._gaussian_segment((center - 118, mouth_y), (center + 118, mouth_y))
        self._gaussian_segment((center - 118, mouth_y), (center - 14, neck_y))
        self._gaussian_segment((center + 118, mouth_y), (center + 14, neck_y))
        # A symmetric triangular hood surrounds the peg field. Its overlap
        # with the funnel throat prevents slipping through an exterior seam.
        for direction in (-1, 1):
            # Keep a full ball-diameter passage beside every exterior peg.
            # One straight roof to the bin corner narrows that passage midway
            # down the triangle and can wedge a ball against an outer pin.
            edge = (GAUSSIAN_ROWS - 1) * GAUSSIAN_PIN_SPACING * .5
            hood = [V(center + direction * 26, neck_y - 3),
                    V(center + direction * 46, first.y),
                    V(center + direction * (edge + 46), last.y),
                    V(center + direction * half, last.y + 25)]
            for start, end in zip(hood, hood[1:]):
                self._gaussian_segment(start, end)
            self._gaussian_segment((center + direction * half, last.y + 25),
                                   (center + direction * half, bottom))
        for row in range(GAUSSIAN_ROWS):
            for column in range(row + 1):
                pos = self.gaussian_pin(row, column)
                pin = pymunk.Circle(self.space.static_body, GAUSSIAN_PIN_RADIUS, pos)
                pin.collision_type = GAUSSIAN_PIN_TYPE
                pin.elasticity, pin.friction = .5, .08
                self.space.add(pin)
                self.gaussian_shapes.append(pin)
                self.gaussian_pin_shapes[pin] = (row, column)
            # The hood connects the physical funnel to the visible peg field.
            # Once the first peg is touched, each animated hop visits exactly
            # the next row and cannot skip a decision or acquire a lateral bias.
        bin_top = last.y + 29
        for index in range(12):
            x = center + (index - 5.5) * GAUSSIAN_PIN_SPACING
            self._gaussian_segment((x, bin_top), (x, bottom), 1.8)
        self._gaussian_segment((center - half, bottom), (center + half, bottom), 2.5)

    def start_gaussian(self, collector=None):
        collector = collector if collector in self.balls else (self.balls[0] if self.balls else None)
        if collector is None:
            return False
        # Only the collector changes. Other balls, projectiles, targets, gravity
        # and the paddle continue in the same space throughout the experiment.
        self.gaussian_collector = collector
        self.gaussian_original = (collector.radius, collector.shape.elasticity,
                                  collector.shape.friction, collector.shape.filter,
                                  collector.shape.sensor, collector.trail.maxlen,
                                  collector.body.body_type, collector.body.mass)
        collector.resize(self.space, GAUSSIAN_BALL_RADIUS)
        collector.shape.sensor = True  # release is controlled for five seconds
        self.gaussian_phase = 'aim'
        self.gaussian_elapsed = self.gaussian_phase_elapsed = 0.0
        self.gaussian_row = 0
        self.gaussian_bin = None
        self.gaussian_prize = 0
        self.gaussian_paid = False
        self.gaussian_fade_left = 0.0
        self.gaussian_shapes = []
        self.gaussian_pin_shapes = {}
        self.gaussian_segments = []
        self.gaussian_contact_rows = set()
        self.gaussian_pin_pulses = []
        self.gaussian_trace.clear()
        self.gaussian_trace_clock = 0.0
        self.gaussian_capture_pending = False
        self.gaussian_column = 0
        self.gaussian_bits = []
        self.gaussian_hop_elapsed = 0.0
        self.gaussian_route_done = False
        self._build_gaussian_board()
        self.gaussian_position = self.gaussian_aim_position()
        self.gaussian_previous = self.gaussian_position
        self.teleport(collector, self.gaussian_position)
        collector.body.velocity = (0, 0)
        collector.body.angular_velocity = 0.0
        self.active_left = GAUSSIAN_AIM_TIME
        return True

    def _gaussian_matches(self, arbiter):
        ball = self.gaussian_collector
        return (self.active == 'gaussian' and self.gaussian_phase == 'fall'
                and ball is not None and ball.shape in arbiter.shapes)

    def _gaussian_solid_pre(self, arbiter, space, data):
        arbiter.process_collision = self._gaussian_matches(arbiter)

    def _gaussian_pin_pre(self, arbiter, space, data):
        arbiter.process_collision = self._gaussian_matches(arbiter)
        if not arbiter.process_collision:
            return
        pin = next((shape for shape in arbiter.shapes if shape in self.gaussian_pin_shapes), None)
        if pin is not None and self.gaussian_pin_shapes[pin] == (0, 0):
            # Never alter body type or remove shapes inside a solver callback.
            # Zero restitution holds the actual contact until the safe tick end.
            self.gaussian_capture_pending = True
            arbiter.restitution = 0.0
        else:
            arbiter.restitution = .5

    def _begin_gaussian_guided(self):
        ball = self.gaussian_collector
        if ball not in self.balls or self.gaussian_phase != 'fall':
            return
        self.gaussian_capture_pending = False
        self.gaussian_phase = 'align'
        self.gaussian_phase_elapsed = 0.0
        ball.body.body_type = pymunk.Body.KINEMATIC
        ball.shape.sensor = True
        ball.body.velocity = (0, 0)
        ball.body.angular_velocity = 0.0
        ball.body.force = (0, 0)
        self.gaussian_hop_start = V(*ball.body.position)
        self.gaussian_hop_end = self.gaussian_pin(0, 0) - V(0, GAUSSIAN_PIN_RADIUS + ball.radius)
        self.gaussian_hop_elapsed = 0.0

    def _gaussian_next_hop(self):
        """One fresh fair bit at this peg; no precomputed or forced outcome."""
        row, column = self.gaussian_row, self.gaussian_column
        if row >= GAUSSIAN_ROWS:
            self.gaussian_phase = 'exit'
            self.gaussian_hop_start = V(*self.gaussian_collector.body.position)
            self.gaussian_hop_end = self.gaussian_bin_position(self.gaussian_column)
            self.gaussian_hop_elapsed = 0.0
            return
        direction = self.rng.getrandbits(1)
        self.gaussian_bits.append(direction)
        self.gaussian_contact_rows.add(row)
        self.gaussian_pin_pulses.append((row, column, self.sim_time))
        self.gaussian_pin_pulses = self.gaussian_pin_pulses[-18:]
        self.gaussian_column += direction
        self.gaussian_row += 1
        self.gaussian_hop_start = V(*self.gaussian_collector.body.position)
        self.gaussian_hop_end = (self.gaussian_pin(self.gaussian_row, self.gaussian_column)
                                - V(0, GAUSSIAN_PIN_RADIUS + GAUSSIAN_BALL_RADIUS))
        self.gaussian_hop_elapsed = 0.0

    def _gaussian_hop_position(self, fraction):
        arc_height = GAUSSIAN_HOP_HEIGHT
        return (self.gaussian_hop_start.interpolate_to(self.gaussian_hop_end, fraction)
                - V(0, 4 * arc_height * fraction * (1 - fraction)))

    def prepare_gaussian(self, controls, dt):
        """Call before EVERY space.step; never steps the physics engine itself."""
        if self.active != 'gaussian' or self.gaussian_collector not in self.balls:
            return
        ball = self.gaussian_collector
        if self.gaussian_phase == 'aim':
            target = self.gaussian_aim_position()
            ball.body.velocity = (target - ball.body.position) / max(dt, 1e-12)
            ball.body.angular_velocity = 0.0
        elif self.gaussian_phase in ('align', 'guided', 'exit'):
            duration = .20 if self.gaussian_phase == 'align' else GAUSSIAN_EXIT_TIME if self.gaussian_phase == 'exit' else GAUSSIAN_HOP_TIME
            if self.gaussian_hop_elapsed + 1e-12 >= duration:
                if self.gaussian_phase == 'exit':
                    self.gaussian_route_done = True
                else:
                    self.gaussian_phase = 'guided'
                    self._gaussian_next_hop()
                duration = GAUSSIAN_EXIT_TIME if self.gaussian_phase == 'exit' else GAUSSIAN_HOP_TIME
            if self.gaussian_route_done:
                ball.body.velocity = (0, 0)
                return
            self.gaussian_hop_elapsed = min(duration, self.gaussian_hop_elapsed + dt)
            fraction = self.gaussian_hop_elapsed / duration
            next_position = (self._gaussian_hop_position(fraction) if self.gaussian_phase == 'guided'
                             else self.gaussian_hop_start.interpolate_to(self.gaussian_hop_end, fraction * fraction * (3 - 2 * fraction)))
            # The solver moves the sensor by this short segment. Existing world
            # sweeps score targets using exactly the same motion the player sees.
            ball.body.velocity = (next_position - ball.body.position) / max(dt, 1e-12)
            ball.body.angular_velocity = 0.0

    def step_gaussian(self, controls, dt):
        """Call once AFTER a normal World tick; the rest of the arena stays live."""
        self.gaussian_fade_left = max(0.0, self.gaussian_fade_left - dt)
        if self.active != 'gaussian' or self.gaussian_phase is None:
            return False
        ball = self.gaussian_collector
        if ball not in self.balls:
            self.finish_powerup()
            return False
        self.gaussian_elapsed += dt
        self.gaussian_phase_elapsed += dt
        self.gaussian_previous = self.gaussian_position
        self.gaussian_position = V(*ball.body.position)
        if self.gaussian_phase == 'aim':
            self.active_left = max(0.0, GAUSSIAN_AIM_TIME - self.gaussian_phase_elapsed)
            if self.gaussian_phase_elapsed + 1e-9 >= GAUSSIAN_AIM_TIME:
                self.gaussian_phase = 'fall'
                self.gaussian_phase_elapsed = 0.0
                ball.shape.sensor = False
                ball.body.velocity = (0, 0)
                ball.body.activate()
            return True
        entrance_y = self.gaussian_pin(0, 0).y - GAUSSIAN_PIN_RADIUS - ball.radius - 5
        if self.gaussian_phase == 'fall' and (self.gaussian_capture_pending or ball.body.position.y >= entrance_y):
            self._begin_gaussian_guided()
        if self.gaussian_phase == 'guided':
            duration = GAUSSIAN_EXIT_TIME if self.gaussian_row == GAUSSIAN_ROWS else GAUSSIAN_HOP_TIME
            self.active_left = max(0.0, (GAUSSIAN_ROWS - self.gaussian_row) * GAUSSIAN_HOP_TIME
                                   + duration - self.gaussian_hop_elapsed)
        else:
            self.active_left = max(0.0, GAUSSIAN_MAX_FALL_TIME - self.gaussian_phase_elapsed)
        self.gaussian_trace_clock += dt
        if self.gaussian_trace_clock >= 1 / 120:
            self.gaussian_trace_clock %= 1 / 120
            self.gaussian_trace.append(V(*ball.body.position))
        if self.gaussian_route_done:
            # Every row contributes one Bernoulli bit: their sum is precisely
            # Binomial(10, .5), regardless of funnel aiming or incoming speed.
            self.gaussian_bin = self.gaussian_column
            self.gaussian_prize = GAUSSIAN_PRIZES[self.gaussian_bin]
            if not self.gaussian_paid:
                self.score += self.gaussian_prize
                self.gaussian_paid = True
                self.gaussian_runs += 1
                self.gaussian_counts[self.gaussian_bin] += 1
                self.gaussian_last_result = (self.gaussian_bin, self.gaussian_prize,
                                             tuple(self.gaussian_bits))
            self.finish_powerup()
            self.message = ('GAUSSIAN ROLL / +' + str(self.gaussian_prize) + ' POINTS'
                            if self.gaussian_prize else 'GAUSSIAN ROLL / CENTRE POCKET')
            self.message_left = 2.8
            return True
        if self.gaussian_phase == 'fall' and self.gaussian_phase_elapsed > GAUSSIAN_MAX_FALL_TIME:
            # A very unusual external interference in the physical funnel must
            # not soft-lock the game. It never awards an unearned pocket prize.
            self.finish_powerup()
            self.message, self.message_left = 'GAUSSIAN ROLL / BOARD RELEASED', 2.8
        return True

    def finish_gaussian(self):
        ball = self.gaussian_collector
        for shape in self.gaussian_shapes:
            if shape.space is self.space:
                self.space.remove(shape)
        self.gaussian_shapes = []
        self.gaussian_pin_shapes = {}
        if ball in self.balls and self.gaussian_original is not None:
            radius, elasticity, friction, shape_filter, sensor, trail_length, body_type, mass = self.gaussian_original
            incoming = V(*ball.body.velocity)
            ball.body.body_type = body_type
            if body_type == pymunk.Body.DYNAMIC:
                ball.body.mass = mass
            ball.resize(self.space, radius)
            ball.shape.elasticity, ball.shape.friction = elasticity, friction
            ball.shape.filter, ball.shape.sensor = shape_filter, sensor
            ball.trail = deque(maxlen=trail_length)
            # A short upward pop restores the ordinary ball below the board;
            # it immediately becomes available to the player's live paddle.
            ball.body.velocity = ((self.gaussian_bits[-1] * 2 - 1) * 105, -260) if self.gaussian_paid else incoming
            self.teleport(ball, self.fit_to_solids(ball.body.position, radius))
            self.burst(ball.body.position, GAUSSIAN_AMBER if self.gaussian_paid else GAUSSIAN_TEAL, 28)
        self.gaussian_phase = None
        self.gaussian_collector = None
        self.gaussian_original = None
        self.gaussian_capture_pending = False
        self.gaussian_fade_left = GAUSSIAN_FADE_TIME


class GaussianRendererMixin:
    def draw_gaussian(self, world, alpha=1.0):
        """Transparent field geometry: call BEFORE ordinary balls and targets."""
        if world.active != 'gaussian' and world.gaussian_fade_left <= 0:
            return
        fade = (1.0 if world.active == 'gaussian' else
                world.gaussian_fade_left / GAUSSIAN_FADE_TIME)
        appear = clamp(world.gaussian_elapsed / .7, 0, 1)
        intensity = fade * appear
        if intensity <= 0:
            return
        teal, amber = GAUSSIAN_TEAL, GAUSSIAN_AMBER
        center = (LEFT + RIGHT) * .5
        first = world.gaussian_pin(0, 0)
        last = world.gaussian_pin(9, 0)
        bin_y = world.gaussian_bin_position(0).y
        # Quiet Gaussian envelope and equal-spaced meridians live directly on
        # the arena background. There is no opaque panel or replacement scene.
        bell = []
        baseline = bin_y - 21
        for step in range(161):
            x = (step / 160 - .5) * GAUSSIAN_PIN_SPACING * 11
            height = math.exp(-.5 * (x / (GAUSSIAN_PIN_SPACING * 1.58)) ** 2)
            bell.append(self.project((center + x, baseline - height * 390)))
        pygame.draw.aalines(self.canvas, self.shade(teal, .16 * intensity), False, bell)
        for index in range(11):
            x = center + (index - 5) * GAUSSIAN_PIN_SPACING
            height = math.exp(-.5 * ((index - 5) / 1.58) ** 2)
            pygame.draw.aaline(self.canvas, self.shade(teal, .035 * intensity),
                               self.project((x, baseline)), self.project((x, baseline - height * 390)))
        for start, end, kind in world.gaussian_segments:
            if kind == 'gate':
                color = self.shade(teal, .11 * intensity)
                pygame.draw.aaline(self.canvas, color, self.project(start), self.project(end))
            else:
                p, q = self.project(start), self.project(end)
                pygame.draw.line(self.canvas, self.shade(teal, .11 * intensity), p, q, 5)
                pygame.draw.aaline(self.canvas, self.shade(teal, .63 * intensity), p, q)
        # Pins materialise in a quick cascade. Each visited peg leaves an
        # expanding ring, and the softly lit core remains easy to distinguish.
        pulses = {(row, column): world.sim_time - at
                  for row, column, at in world.gaussian_pin_pulses
                  if world.sim_time - at < .65}
        for row in range(GAUSSIAN_ROWS):
            growth = clamp((world.gaussian_elapsed - row * .036) / .28, 0, 1)
            radius = max(1, round(GAUSSIAN_PIN_RADIUS * DRAW_SCALE * growth))
            for column in range(row + 1):
                p = self.project(world.gaussian_pin(row, column))
                pulse = pulses.get((row, column))
                live = 1 - pulse / .65 if pulse is not None else 0
                color = amber if live else teal
                pygame.draw.circle(self.canvas, self.shade(color, (.08 + live * .16) * intensity), p, radius + 4)
                pygame.draw.circle(self.canvas, self.shade(color, (.38 + live * .5) * intensity), p, radius, 1)
                pygame.draw.circle(self.canvas, self.shade(color, (.44 + live * .5) * intensity), p, max(1, radius // 3))
                pygame.draw.circle(self.canvas, self.shade(INK, .65 * intensity), p - V(radius * .27, radius * .3), 1)
                if live:
                    pygame.draw.circle(self.canvas, self.shade(amber, live * .56 * intensity), p,
                                       max(1, round(radius + pulse * 36)), 1)
        for index, prize in enumerate(GAUSSIAN_PRIZES):
            pos = self.project(world.gaussian_bin_position(index))
            selected = world.gaussian_paid and world.gaussian_bin == index
            color = amber if prize else teal
            if selected:
                pygame.draw.circle(self.canvas, self.shade(amber, .22 * fade), pos,
                                   max(1, round(18 + (1 - fade) * 35)), 2)
            brightness = 1.0 if selected else .57
            self.label(str(prize), (pos.x, pos.y - 16), 16,
                       self.shade(color, brightness * intensity), True)
            pygame.draw.line(self.canvas, self.shade(color, (.9 if selected else .2) * intensity),
                             (pos.x - 12, pos.y + 7), (pos.x + 12, pos.y + 7), 2)
        if len(world.gaussian_trace) >= 2:
            points = [self.project(p) for p in world.gaussian_trace]
            # Short translucent trail stays behind the game's own ball/trail.
            pygame.draw.aalines(self.canvas, self.shade(teal, .2 * intensity), False, points)
        label_y = first.y - 106
        label_pos = self.project((center + 225, label_y))
        self.label('GAUSSIAN ROLL', label_pos, 18, self.shade(teal, .65 * intensity), True)
        if world.gaussian_phase == 'aim':
            remaining = max(0.0, GAUSSIAN_AIM_TIME - world.gaussian_phase_elapsed)
            self.label(f'{remaining:04.1f}', label_pos + V(0, 31), 30,
                       self.shade(amber, .78 * intensity), True)
            self.label('A / D  AIM', label_pos + V(0, 59), 14,
                       self.shade(teal, .55 * intensity), True)
            aim = self.project(world.gaussian_aim_position())
            pygame.draw.line(self.canvas, self.shade(amber, .21 * intensity),
                             aim + V(0, 9), aim + V(0, 30), 1)
            pygame.draw.lines(self.canvas, self.shade(amber, .7 * intensity), False,
                              [aim + V(-4, 25), aim + V(0, 30), aim + V(4, 25)], 1)
        elif world.gaussian_phase == 'fall':
            self.label('ENTERING THE FUNNEL', label_pos + V(0, 28), 14,
                       self.shade(teal, .44 * intensity), True)
        elif world.gaussian_phase in ('align', 'guided', 'exit'):
            self.label('50 / 50  EACH PEG', label_pos + V(0, 28), 14,
                       self.shade(teal, .5 * intensity), True)
            self.label(f'{world.gaussian_row:02d} / 10', label_pos + V(0, 50), 19,
                       self.shade(amber, .72 * intensity), True)
        elif world.gaussian_paid:
            self.label('+' + str(world.gaussian_prize), label_pos + V(0, 30), 34,
                       self.shade(amber, intensity), True)


DRONE_COLOR = (115, 238, 213)
DRONE_ACCENT = (255, 184, 93)
DRONE_PROXY_RADIUS = 20.0
DRONE_GRAVITY = GRAVITY * 1.65
DRONE_THRUST = DRONE_GRAVITY * 2.15
DRONE_MAX_ROLL_RATE = 6.8
DRONE_ROLL_RESPONSE = 14.0
DRONE_DRAG = .04
DRONE_MAX_SPEED = 725.0
DRONE_BOMB_COOLDOWN = .65
DRONE_BOMB_RADIUS = 6.0
DRONE_SHRAPNEL_SPEED = 1050.0
DRONE_SHRAPNEL_RADIUS = 3.6
DRONE_SHRAPNEL_LIFETIME = 3.2


@dataclass
class DroneBomb:
    position: V
    previous: V
    velocity: V
    age: float = 0.0
    angle: float = 0.0


@dataclass
class DroneShard:
    position: V
    previous: V
    velocity: V
    left: float
    trail: object


@dataclass
class DroneBlast:
    position: V
    left: float = .52


@dataclass
class DroneCrash:
    position: V
    inward: V
    incoming: V


@dataclass
class DroneDebris:
    position: V
    velocity: V
    angle: float
    spin: float
    size: float
    left: float


class DroneMixin:
    """Rate-controlled ACRO body; Pymunk handles actual circular contacts.

    A circular collision proxy encloses the rendered rotor tips. Normal target
    sweeps use that same radius. Contacts with every arena boundary (including
    the floor) crash; balls and the stationary paddle remain ordinary solids.
    Only the collecting ball receives thrust. No global gravity modifications.
    """

    def init_drone(self):
        self.drone_collector = None
        self.drone_original_radius = BALL_RADIUS
        self.drone_throttle = 0.0
        self.drone_roll_rate = 0.0
        self.drone_roll_input = 0.0
        self.drone_crash = None
        self.drone_previous_angle = 0.0
        self.drone_debris = []
        self.drone_waiting = False
        self.drone_platform_position = V(0, 0)
        self.drone_platform_fade = 0.0
        self.drone_bomb_held = False
        self.drone_bomb_ready_at = 0.0
        self.drone_bombs = []
        self.drone_shards = []
        self.drone_blasts = []

    def start_drone(self, collector=None):
        collector = collector if collector in self.balls else (self.balls[0] if self.balls else None)
        if collector is None:
            return
        self.drone_collector = collector
        self.drone_original_radius = collector.radius
        self.drone_throttle = 0.0
        self.drone_roll_rate = self.drone_roll_input = 0.0
        self.drone_crash = None
        self.drone_previous_angle = 0.0
        collector.resize(self.space, max(collector.radius, DRONE_PROXY_RADIUS))
        self.teleport(collector, self.fit_to_solids(collector.body.position, collector.radius))
        collector.body.velocity = (0, 0)
        collector.body.angle = collector.body.angular_velocity = 0.0
        # A suspended hull cannot gain gravity or accidental contact impulses.
        # The holographic support has no collision effect on other balls.
        self.drone_waiting = True
        self.drone_platform_position = V(*collector.body.position)
        self.drone_platform_fade = 0.0
        self.drone_bomb_held = False
        self.drone_bomb_ready_at = self.sim_time
        self.space.remove(collector.shape, collector.body)
        self.paddle.velocity = (0, 0)
        self.paddle.angular_velocity = 0.0
        self.burst(collector.body.position, DRONE_COLOR, 26)

    def release_drone_platform(self):
        """A fresh gameplay keydown releases the hull; held keys cannot do so."""
        ball = self.drone_collector
        if self.active != 'drone' or not self.drone_waiting or ball not in self.balls:
            return False
        self.drone_waiting = False
        self.drone_platform_fade = .4
        self.active_left = POWER_DURATION
        if ball.body.space is None:
            self.space.add(ball.body, ball.shape)
        self.teleport(ball, self.fit_to_solids(ball.body.position, ball.radius))
        ball.body.velocity = (0, 0)
        ball.body.angle = ball.body.angular_velocity = 0.0
        ball.body.activate()
        self.burst(ball.body.position + V(0, ball.radius), DRONE_COLOR, 12)
        return True

    def prepare_drone(self, controls, dt):
        if self.active != 'drone' or self.drone_collector not in self.balls:
            return
        ball = self.drone_collector
        if self.drone_waiting:
            self.drone_throttle = self.drone_roll_input = self.drone_roll_rate = 0.0
            return
        pressed = bool(getattr(controls, 'bomb', False))
        if pressed and not self.drone_bomb_held:
            self.drop_drone_bomb()
        self.drone_bomb_held = pressed
        # A/D turn the hull. L/right is a momentary engine switch: releasing
        # it removes thrust immediately while preserving the flight velocity.
        self.drone_throttle = float(bool(controls.throttle))
        self.drone_roll_input = clamp(controls.move, -1, 1)
        target_rate = self.drone_roll_input * DRONE_MAX_ROLL_RATE
        old_rate = self.drone_roll_rate
        decay = math.exp(-DRONE_ROLL_RESPONSE * dt)
        self.drone_roll_rate = target_rate + (old_rate - target_rate) * decay
        # The exact average rate produces the same angle for a constant stick
        # input regardless of how the physics tick is divided into substeps.
        average_rate = target_rate + (old_rate - target_rate) * (1 - decay) / (DRONE_ROLL_RESPONSE * dt)
        ball.body.angular_velocity = average_rate
        angle_midpoint = ball.body.angle + average_rate * dt * .5
        up = V(math.sin(angle_midpoint), -math.cos(angle_midpoint))
        ball.body.velocity += up * (DRONE_THRUST * self.drone_throttle * dt)
        # Extra gravity is local to the drone; other balls keep normal physics.
        ball.body.velocity += V(0, DRONE_GRAVITY - self.space.gravity.y) * dt
        ball.body.velocity *= math.exp(-DRONE_DRAG * dt)
        ball.limit_speed(DRONE_MAX_SPEED)
        ball.body.activate()

    def record_drone_wall(self, arbiter):
        """Callback only records; removing shapes here would lock Pymunk."""
        if self.active != 'drone' or self.drone_collector is None or self.drone_waiting:
            return
        ball = self.drone_collector
        shapes = arbiter.shapes
        for index, shape in enumerate(shapes):
            if shape.body is ball.body:
                inward = arbiter.normal * (-1 if index == 0 else 1)
                self._record_drone_crash(ball.body.position, inward, ball.body.velocity)
                return

    def _record_drone_crash(self, position, inward, incoming):
        if self.drone_crash is None:
            self.drone_crash = DroneCrash(V(*position), V(*inward), V(*incoming))
        elif self.drone_crash.inward.dot(inward) < .5:
            # Both faces of a corner must push the released ball inward.
            self.drone_crash.inward += inward

    def check_drone_bounds(self):
        """Fallback for direct/manual teleports and conservative containment."""
        if self.active != 'drone' or self.drone_collector is None or self.drone_waiting:
            return
        ball = self.drone_collector
        pos, radius = ball.body.position, ball.radius
        lo_x, hi_x = LEFT + 8 + radius, RIGHT - 8 - radius
        lo_y, hi_y = TOP + 8 + radius, BOTTOM - 8 - radius
        for over, normal in ((pos.x < lo_x - .05, V(1, 0)),
                             (pos.x > hi_x + .05, V(-1, 0)),
                             (pos.y < lo_y - .05, V(0, 1)),
                             (pos.y > hi_y + .05, V(0, -1))):
            if over:
                self._record_drone_crash(pos, normal, ball.body.velocity)

    def resolve_drone_crash(self):
        """After space.step: end flight and return its final scoring endpoint.

        Caller uses this endpoint for the crashed body's sweep so the emergency
        separation cannot count as a flight through obstacles beyond the wall.
        """
        self.check_drone_bounds()
        if self.active != 'drone' or self.drone_crash is None:
            return None
        ball = self.drone_collector
        pos, r = self.drone_crash.position, ball.radius
        endpoint = V(clamp(pos.x, LEFT + 8 + r, RIGHT - 8 - r),
                     clamp(pos.y, TOP + 8 + r, BOTTOM - 8 - r))
        self.finish_powerup()
        self.message, self.message_left = 'SIGNAL LOST / BALL RECOVERED', 2.4
        return ball, endpoint

    def finish_drone(self):
        ball, crash = self.drone_collector, self.drone_crash
        if ball is not None and ball in self.balls:
            if ball.body.space is None:
                self.space.add(ball.body, ball.shape)
            origin = V(*ball.body.position)
            velocity = V(*ball.body.velocity)
            if crash is not None:
                direction = crash.inward.normalized() if crash.inward.length_squared > 1e-12 else V(0, -1)
                tangent = crash.incoming - direction * crash.incoming.dot(direction)
                velocity = direction * clamp(crash.incoming.length * .8, 450, 1100) + tangent * .25
                origin = V(*crash.position)
                self._spawn_drone_debris(origin, crash.incoming)
                self.burst(origin, DRONE_ACCENT, 54)
            else:
                self.burst(origin, DRONE_COLOR, 24)
            ball.resize(self.space, self.drone_original_radius)
            ball.body.angle = ball.body.angular_velocity = 0.0
            if not all(math.isfinite(component) for component in velocity):
                velocity = V(0, -450)
            ball.body.velocity = velocity
            ball.limit_speed(MAX_BALL_SPEED)
            radius = ball.radius
            origin = V(clamp(origin.x, LEFT + 8 + radius + 2, RIGHT - 8 - radius - 2),
                       clamp(origin.y, TOP + 8 + radius + 2, BOTTOM - 8 - radius - 2))
            self.teleport(ball, self.fit_to_solids(origin, radius))
            ball.body.activate()
        self.drone_collector = None
        self.drone_waiting = False
        self.drone_platform_fade = 0.0
        self.drone_crash = None
        self.drone_roll_rate = self.drone_roll_input = 0.0
        self.paddle.velocity = (0, 0)
        self.paddle.angular_velocity = 0.0

    def drop_drone_bomb(self):
        ball = self.drone_collector
        if (self.active != 'drone' or self.drone_waiting or ball not in self.balls
                or self.sim_time + 1e-10 < self.drone_bomb_ready_at):
            return False
        # Drop along world gravity even during a flip. Inherit momentum, but
        # give a slight downward release so a level hover can actually drop it.
        origin = V(*ball.body.position) + V(0, ball.radius + DRONE_BOMB_RADIUS + 2)
        origin = V(origin.x, min(origin.y, BOTTOM - 8 - DRONE_BOMB_RADIUS))
        velocity = V(*ball.body.velocity) + V(0, 65)
        self.drone_bombs.append(DroneBomb(origin, V(*origin), velocity))
        self.drone_bomb_ready_at = self.sim_time + DRONE_BOMB_COOLDOWN
        return True

    def detonate_drone_bomb(self, origin):
        """Exactly five incandescent rays, with deterministic upward spread."""
        origin = V(*origin)
        self.drone_blasts.append(DroneBlast(origin))
        self.burst(origin, DRONE_ACCENT, 28)
        # Five spokes cover the half-plane above the floor. No gameplay RNG
        # is spent on visuals and no grace period makes a hovering drone safe.
        for degrees in (-162, -126, -90, -54, -18):
            angle = math.radians(degrees)
            velocity = V(math.cos(angle), math.sin(angle)) * DRONE_SHRAPNEL_SPEED
            point = origin + velocity.normalized() * (DRONE_SHRAPNEL_RADIUS + 1)
            self.drone_shards.append(DroneShard(point, V(*point), velocity,
                                                DRONE_SHRAPNEL_LIFETIME, deque(maxlen=14)))

    def step_drone_ordnance(self, dt, hit_targets=None, drone_start=None):
        """Swept ordnance contacts after each Pymunk substep, outside callbacks.

        The optional drone_start is its position before the same physics
        substep. Relative sweeps catch crossing trajectories even if both
        endpoints are outside the drone; after flight, shrapnel only scores.
        """
        if not self.drone_bombs and not self.drone_shards:
            return None
        floor = BOTTOM - 8 - DRONE_BOMB_RADIUS
        live_bombs = []
        detonated = []
        for bomb in self.drone_bombs:
            bomb.previous = V(*bomb.position)
            bomb.age += dt
            # Analytic ballistic integration removes timestep-dependent drift.
            bomb.position += bomb.velocity * dt + V(0, .5 * GRAVITY * dt * dt)
            bomb.velocity += V(0, GRAVITY * dt)
            bomb.angle += dt * (2.0 + bomb.velocity.x * .006)
            if bomb.position.y >= floor:
                distance = bomb.position.y - bomb.previous.y
                fraction = clamp((floor - bomb.previous.y) / distance, 0, 1) if distance > 1e-10 else 0
                impact = bomb.previous + (bomb.position - bomb.previous) * fraction
                impact = V(impact.x, floor)
                detonated.append((impact, dt * (1 - fraction)))
            elif bomb.age < 6.0 and LEFT - 20 < bomb.position.x < RIGHT + 20:
                live_bombs.append(bomb)
        self.drone_bombs = live_bombs
        # Newly emitted rays only use the unconsumed part of this substep.
        old_count = len(self.drone_shards)
        shard_times = [dt] * old_count
        for origin, remaining in detonated:
            self.detonate_drone_bomb(origin)
            shard_times.extend([remaining] * 5)
        hits = {} if hit_targets is None else hit_targets
        live_shards = []
        ball = self.drone_collector if self.active == 'drone' and not self.drone_waiting else None
        drone_end = V(*ball.body.position) if ball is not None else None
        start_position = V(*drone_start) if drone_start is not None and ball is not None else drone_end
        for shard, age in zip(self.drone_shards, shard_times):
            shard.previous = V(*shard.position)
            shard.position += shard.velocity * age
            shard.left -= age
            # Store trails at a distance cadence, independent of tiny substeps.
            if not shard.trail or (shard.position - shard.trail[-1]).length_squared >= 36:
                shard.trail.append(V(*shard.position))
            for index, target in self.active_targets():
                if (index not in hits and self.target_ready(index)
                        and swept_circle(shard.previous, shard.position, target,
                                         DRONE_SHRAPNEL_RADIUS + TARGET_RADIUS)):
                    hits[index] = None
            if ball is not None:
                # A newborn shard sees only the matching tail of hull motion.
                fraction = age / dt if dt > 0 else 0
                hull_start = drone_end + (start_position - drone_end) * fraction
                if swept_circle(shard.previous - hull_start, shard.position - drone_end,
                                V(0, 0), ball.radius + DRONE_SHRAPNEL_RADIUS):
                    away = -shard.velocity.normalized()
                    self._record_drone_crash(drone_end, away, ball.body.velocity)
            if (shard.left > 0 and LEFT - 20 < shard.position.x < RIGHT + 20
                    and TOP - 20 < shard.position.y < BOTTOM + 20):
                live_shards.append(shard)
        self.drone_shards = live_shards
        if hit_targets is None:
            for index in hits:
                self.award_target(None, target_index=index)
        return self.resolve_drone_crash() if self.drone_crash is not None else None

    def _spawn_drone_debris(self, origin, incoming):
        if not self.effects:
            return
        for index in range(12):
            phase = self.fx_rng.uniform(0, math.tau)
            velocity = V(math.cos(phase), math.sin(phase)) * self.fx_rng.uniform(90, 340)
            self.drone_debris.append(DroneDebris(V(*origin), velocity + incoming * .12,
                                                phase, self.fx_rng.uniform(-13, 13),
                                                self.fx_rng.uniform(3, 9), .85))
        self.drone_debris = self.drone_debris[-24:]

    def tick_drone_effects(self, dt):
        self.drone_platform_fade = max(0.0, self.drone_platform_fade - dt)
        for blast in self.drone_blasts:
            blast.left -= dt
        self.drone_blasts = [blast for blast in self.drone_blasts if blast.left > 0]
        for fragment in self.drone_debris:
            fragment.left -= dt
            fragment.velocity += V(0, 260) * dt
            fragment.position += fragment.velocity * dt
            fragment.angle += fragment.spin * dt
        self.drone_debris = [fragment for fragment in self.drone_debris if fragment.left > 0]


class DroneRendererMixin:
    def draw_drone_ordnance(self, world, alpha):
        if world.drone_waiting or world.drone_platform_fade > 0:
            center = self.project(world.drone_platform_position)
            fade = 1.0 if world.drone_waiting else world.drone_platform_fade / .4
            y = center.y + world.drone_collector.radius * DRAW_SCALE * .55 if world.drone_collector else center.y + 10
            spread = 33 + (1 - fade) * 25
            color = self.shade(DRONE_COLOR, fade)
            pygame.draw.line(self.canvas, self.shade(DRONE_COLOR, fade * .15), (center.x - spread, y + 3), (center.x + spread, y + 3), 9)
            pygame.draw.line(self.canvas, color, (center.x - spread, y), (center.x + spread, y), 2)
            for side in (-1, 1):
                pygame.draw.lines(self.canvas, self.shade(DRONE_COLOR, fade * .5), False,
                                  [(center.x + side * spread, y), (center.x + side * 24, y + 8),
                                   (center.x + side * 10, y + 8)], 1)
            if world.drone_waiting:
                self.label('PRESS A KEY TO LAUNCH', (center.x, y + 29), 14, DRONE_COLOR, True)
        for bomb in world.drone_bombs:
            point = self.project(bomb.previous.interpolate_to(bomb.position, alpha))
            r = max(3, round(DRONE_BOMB_RADIUS * DRAW_SCALE))
            axis = V(math.sin(bomb.angle), -math.cos(bomb.angle))
            self.halo(point, DRONE_ACCENT, 12)
            pygame.draw.circle(self.canvas, (75, 62, 37), point, r)
            pygame.draw.circle(self.canvas, DRONE_ACCENT, point, r, 1)
            pygame.draw.line(self.canvas, INK, point + axis * r, point + axis * (r + 3), 2)
            spark = point + axis * (r + 5)
            pygame.draw.circle(self.canvas, GOLD, spark, 2 if int(world.sim_time * 24) % 2 else 1)
        for shard in world.drone_shards:
            point = self.project(shard.previous.interpolate_to(shard.position, alpha))
            fade = min(1.0, shard.left / .45)
            if len(shard.trail) >= 2:
                points = [self.project(p) for p in shard.trail]
                pygame.draw.lines(self.canvas, self.shade(DRONE_ACCENT, .16 * fade), False, points, 5)
                pygame.draw.aalines(self.canvas, self.shade(DRONE_ACCENT, .75 * fade), False, points)
            self.halo(point, self.shade(DRONE_ACCENT, fade), 13)
            pygame.draw.circle(self.canvas, self.shade(INK, fade), point, 2)
        for blast in world.drone_blasts:
            age = .52 - blast.left
            point = self.project(blast.position)
            for delay in (0, .065):
                t = max(0, age - delay)
                radius = max(1, round((8 + 185 * t) * DRAW_SCALE))
                pygame.draw.circle(self.canvas, self.shade(DRONE_ACCENT, max(0, 1 - t / .52)), point, radius, 2)

    def draw_drone_background(self, world):
        if world.active != 'drone' or world.drone_collector is None:
            return
        # A faint instrument engraving lives behind play, without a panel.
        if not hasattr(self, '_drone_hud'):
            self._drone_hud = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        layer = self._drone_hud
        layer.fill((0, 0, 0, 0))
        color, accent = DRONE_COLOR, DRONE_ACCENT
        def caption(value, center, size=18, opacity=76, tint=color):
            text = self.text(value, size, tint).copy()
            text.set_alpha(opacity)
            layer.blit(text, text.get_rect(center=center))
        x, top, bottom = 567, 380, 565
        pygame.draw.line(layer, (*color, 30), (x, top), (x, bottom), 3)
        for index in range(11):
            y = top + (bottom - top) * index / 10
            size = 15 if index % 5 == 0 else 7
            pygame.draw.line(layer, (*color, 38), (x - size, y), (x + size, y), 1)
        held = world.drone_throttle > .5
        level = top if held else bottom
        if held:
            pygame.draw.line(layer, (*color, 42), (x, top), (x, bottom), 10)
        pygame.draw.circle(layer, (*color, 76), (x, level), 9, 2)
        pygame.draw.line(layer, (*color, 65), (x - 23, level), (x + 23, level), 1)
        caption('100' if held else '0', (466, 464), 70, 45)
        caption('THRUST', (468, 517), 17, 62)
        caption('HOLD L / RIGHT', (527, 604), 16, 80)
        # Horizontal rate slider plus an attitude ring, with no self-leveling.
        cx, cy, radius = 945, 472, 96
        pygame.draw.circle(layer, (*color, 22), (cx, cy), radius, 1)
        for index in range(24):
            angle = index * math.tau / 24
            axis = V(math.cos(angle), math.sin(angle))
            pygame.draw.line(layer, (*color, 38), V(cx, cy) + axis * (radius - 5),
                             V(cx, cy) + axis * (radius + (7 if index % 3 == 0 else 1)), 1)
        bank = world.drone_collector.body.angle
        axis = V(math.cos(bank), math.sin(bank))
        pygame.draw.line(layer, (*accent, 64), V(cx, cy) - axis * 66, V(cx, cy) + axis * 66, 2)
        pygame.draw.circle(layer, (*accent, 72), (cx, cy), 5, 1)
        for xx in (cx - 166, cx + 166):
            pygame.draw.line(layer, (*color, 33), (xx, cy), (xx + (34 if xx < cx else -34), cy), 1)
        roll = clamp(world.drone_roll_rate / DRONE_MAX_ROLL_RATE, -1, 1)
        pygame.draw.line(layer, (*color, 29), (cx - 150, 607), (cx + 150, 607), 2)
        for index in range(9):
            xx = cx - 150 + index * 37.5
            pygame.draw.line(layer, (*color, 36), (xx, 602), (xx, 612), 1)
        pygame.draw.circle(layer, (*accent, 85), (round(cx + roll * 150), 607), 7, 2)
        caption('A / D  ROLL', (cx, 644), 17, 76)
        caption('FREE ROTATION', (cx, 340), 19, 46)
        caption('LEFT: DROP GRENADE', (800, 703), 17, 77, accent)
        self.canvas.blit(layer, (0, 0))

    def draw_drone_body(self, world, ball, position, radius, alpha):
        if world.active != 'drone' or ball is not world.drone_collector:
            return False
        s, color = self.canvas, DRONE_COLOR
        angle = world.drone_previous_angle * (1 - alpha) + ball.body.angle * alpha
        r = radius
        def point(x, y):
            return position + V(x * r, y * r).rotated(angle)
        self.halo(position, color, max(18, round(r * 1.9)))
        throttle = world.drone_throttle
        phase = world.sim_time * (35 + throttle * 150)
        for side in (-1, 1):
            # Exhaust is just light; rotor tips and body fit inside the proxy.
            rotor = point(side * .61, -.16)
            tip = point(side * .61, .25 + throttle * (1.7 + .3 * math.sin(phase)))
            pygame.draw.polygon(s, self.shade(color, .10 + throttle * .12),
                                (point(side * .61 - .22, -.03),
                                 point(side * .61 + .22, -.03), tip))
            pygame.draw.line(s, self.shade(color, .62), point(side * .22, .05), rotor, max(2, round(r * .17)))
            ellipse = [rotor + V(math.cos(t) * r * .33, math.sin(t) * r * .12).rotated(angle)
                       for t in (i * math.tau / 20 for i in range(20))]
            pygame.draw.aalines(s, color, True, ellipse)
            blade = V(math.cos(phase) * r * .32, math.sin(phase) * r * .11).rotated(angle)
            pygame.draw.line(s, INK, rotor - blade, rotor + blade, 2)
            pygame.draw.circle(s, DRONE_ACCENT if side < 0 else color, rotor, max(1, round(r * .09)))
            for index in range(3):
                t = ((world.sim_time * (1.7 + throttle * 2) + index / 3) % 1)
                spark = point(side * .61 + .04 * math.sin(phase + index), .15 + t * (1.1 + throttle * 2))
                pygame.draw.circle(s, self.shade(color, throttle * (1 - t) * .7), spark, max(1, round(2 * (1 - t))))
        hull = [point(x, y) for x, y in ((-.33, -.24), (-.14, -.44), (.2, -.4),
                                       (.37, -.12), (.26, .25), (-.26, .25))]
        pygame.draw.polygon(s, (28, 56, 63), hull)
        pygame.draw.aalines(s, INK, True, hull)
        pygame.draw.line(s, color, point(-.2, -.24), point(.16, -.29), 2)
        pygame.draw.circle(s, BG, point(.04, .03), max(2, round(r * .17)))
        pygame.draw.circle(s, color, point(.04, .03), max(1, round(r * .08)))
        for side in (-1, 1):
            pygame.draw.line(s, MUTED, point(side * .23, .23), point(side * .36, .46), 2)
            pygame.draw.line(s, INK, point(side * .29, .46), point(side * .45, .46), 1)
        return True

    def draw_drone_debris(self, world):
        for fragment in world.drone_debris:
            center = self.project(fragment.position)
            length = fragment.size * DRAW_SCALE
            axis = V(math.cos(fragment.angle), math.sin(fragment.angle)) * length
            normal = V(-axis.y, axis.x) * .3
            color = self.shade(DRONE_ACCENT, clamp(fragment.left / .85, 0, 1))
            pygame.draw.polygon(self.canvas, color, (center - axis, center + normal, center + axis))


import ast
import re


ANALYTICAL_COLOR = (124, 213, 255)
ANALYTICAL_ACCENT = (197, 153, 255)
ANALYTICAL_UNIT = 62.5  # 50 screen pixels per Cartesian unit.
ANALYTICAL_MAX_POINTS = 28000
ANALYTICAL_MAX_EVALUATIONS = 140000
ANALYTICAL_MAX_PHASE = 2300.0
ANALYTICAL_INPUT_LIMIT = 256
ANALYTICAL_PHANTOM_COUNT = 4
ANALYTICAL_PANEL_IDLE_ALPHA = 42


class AnalyticalExpressionError(ValueError):
    pass


class AnalyticalDomainError(AnalyticalExpressionError):
    pass


class _AnalyticalRefine(Exception):
    pass


class AnalyticalExpression:
    """Parse a tiny arithmetic language; never execute Python supplied by a user.

    Interval evaluation is used to avoid connecting across poles or jumps and
    to resolve every trigonometric phase, including waves hidden by aliasing.
    """
    FUNCTIONS = {
        'sqrt': math.sqrt, 'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
        'ln': math.log, 'abs': abs, 'floor': math.floor, 'roof': math.ceil,
        'sinh': math.sinh, 'cosh': math.cosh, 'tanh': math.tanh,
        'arcsin': math.asin, 'arccos': math.acos, 'arctan': math.atan,
    }
    CONSTANTS = {'e': math.e, 'pi': math.pi, 'phi': (1 + math.sqrt(5)) / 2}
    TOKEN = re.compile(r'\s*(?:(\d+(?:\.\d*)?(?:[eE][+-]?\d+)?|\.\d+(?:[eE][+-]?\d+)?)|([A-Za-z_]+)|([+\-*/^()]))')

    def __init__(self, source):
        if not isinstance(source, str) or len(source) > ANALYTICAL_INPUT_LIMIT:
            raise AnalyticalExpressionError('Keep the expression within 256 characters.')
        source = source.strip().replace('φ', 'phi').replace('ϕ', 'phi').replace('π', 'pi')
        if not source:
            raise AnalyticalExpressionError('Type a function of x, for example sin(x).')
        tokens, position = [], 0
        while position < len(source):
            match = self.TOKEN.match(source, position)
            if match is None:
                raise AnalyticalExpressionError('Use numbers, x, functions and arithmetic symbols only.')
            number, name, operator = match.groups()
            token = number or name or operator
            if name:
                token = {'sen': 'sin', 'ceil': 'roof', 'asin': 'arcsin',
                         'acos': 'arccos', 'atan': 'arctan'}.get(name.lower(), name.lower())
                if token not in self.FUNCTIONS and token not in self.CONSTANTS and token != 'x':
                    raise AnalyticalExpressionError(f'Unknown name: {name[:24]}.')
            tokens.append(token)
            position = match.end()
        if len(tokens) > 150:
            raise AnalyticalExpressionError('This expression has too many operations.')
        normalized = []
        for index, token in enumerate(tokens):
            if index:
                previous = tokens[index - 1]
                left_value = previous == ')' or previous in self.CONSTANTS or previous == 'x' or previous[0].isdigit() or previous[0] == '.'
                right_value = token == '(' or token in self.CONSTANTS or token == 'x' or token in self.FUNCTIONS or token[0].isdigit() or token[0] == '.'
                if left_value and right_value:
                    normalized.append('*')
            normalized.append('**' if token == '^' else token)
        try:
            self.tree = ast.parse(''.join(normalized), mode='eval').body
        except (SyntaxError, RecursionError, MemoryError):
            raise AnalyticalExpressionError('Check the operators and matching parentheses.') from None
        self.nodes = 0
        self._validate(self.tree, 0)
        self.source = source

    def _validate(self, node, depth):
        self.nodes += 1
        if depth > 24 or self.nodes > 96:
            raise AnalyticalExpressionError('Simplify the expression: too many nested operations.')
        if isinstance(node, ast.Constant) and type(node.value) in (int, float):
            try:
                self._finite(float(node.value))
            except (OverflowError, ValueError):
                raise AnalyticalExpressionError('Numeric constants must be finite and below 1e12.') from None
        elif isinstance(node, ast.Name) and node.id in (*self.CONSTANTS, 'x'):
            pass
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            self._validate(node.operand, depth + 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Pow)):
            self._validate(node.left, depth + 1)
            self._validate(node.right, depth + 1)
        elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
              and node.func.id in self.FUNCTIONS and len(node.args) == 1 and not node.keywords):
            self._validate(node.args[0], depth + 1)
        else:
            raise AnalyticalExpressionError('Each supported function takes one parenthesized argument.')

    @staticmethod
    def _finite(value):
        if not math.isfinite(value) or abs(value) > 1e12:
            raise AnalyticalDomainError('The function exceeds the numeric range here.')
        return float(value)

    @staticmethod
    def _power(base, exponent):
        if abs(exponent) > 128:
            raise AnalyticalDomainError('Exponents must stay between -128 and 128.')
        if base < 0 and abs(exponent - round(exponent)) > 1e-12:
            raise AnalyticalDomainError('A fractional power of a negative number is not real.')
        if base == 0 and exponent <= 0:
            raise AnalyticalDomainError('This power is undefined at zero.')
        try:
            return AnalyticalExpression._finite(math.pow(base, exponent))
        except (OverflowError, ValueError):
            raise AnalyticalDomainError('This power exceeds its real numeric range.') from None

    def value(self, x, node=None):
        node = self.tree if node is None else node
        try:
            if isinstance(node, ast.Constant):
                result = float(node.value)
            elif isinstance(node, ast.Name):
                result = x if node.id == 'x' else self.CONSTANTS[node.id]
            elif isinstance(node, ast.UnaryOp):
                result = self.value(x, node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
            elif isinstance(node, ast.BinOp):
                a, b = self.value(x, node.left), self.value(x, node.right)
                if isinstance(node.op, ast.Add):
                    result = a + b
                elif isinstance(node.op, ast.Sub):
                    result = a - b
                elif isinstance(node.op, ast.Mult):
                    result = a * b
                elif isinstance(node.op, ast.Div):
                    if abs(b) < 1e-14:
                        raise AnalyticalDomainError('Division by zero.')
                    result = a / b
                else:
                    result = self._power(a, b)
            else:
                name, argument = node.func.id, self.value(x, node.args[0])
                if name == 'tan' and abs(math.cos(argument)) < 1e-10:
                    raise AnalyticalDomainError('tan is undefined at this angle.')
                result = self.FUNCTIONS[name](argument)
            return self._finite(result)
        except (OverflowError, ZeroDivisionError, ValueError) as error:
            if isinstance(error, AnalyticalExpressionError):
                raise
            raise AnalyticalDomainError('The function is not defined here in the real numbers.') from None

    def interval(self, x0, x1, node=None, resolve=False):
        """Conservative real range, with explicit pole and branch-cut checks."""
        node = self.tree if node is None else node
        if isinstance(node, ast.Constant):
            return float(node.value), float(node.value)
        if isinstance(node, ast.Name):
            return (x0, x1) if node.id == 'x' else (self.CONSTANTS[node.id],) * 2
        if isinstance(node, ast.UnaryOp):
            a, b = self.interval(x0, x1, node.operand, resolve)
            return (-b, -a) if isinstance(node.op, ast.USub) else (a, b)
        if isinstance(node, ast.BinOp):
            a, b = self.interval(x0, x1, node.left, resolve)
            c, d = self.interval(x0, x1, node.right, resolve)
            if isinstance(node.op, ast.Add):
                result = a + c, b + d
            elif isinstance(node.op, ast.Sub):
                result = a - d, b - c
            elif isinstance(node.op, ast.Mult):
                values = a * c, a * d, b * c, b * d
                result = min(values), max(values)
            elif isinstance(node.op, ast.Div):
                if c <= 0 <= d:
                    raise AnalyticalDomainError('A denominator reaches zero.')
                values = a / c, a / d, b / c, b / d
                result = min(values), max(values)
            else:
                if abs(c - d) < 1e-12 and abs(c - round(c)) < 1e-12:
                    exponent = round(c)
                    if exponent <= 0 and a <= 0 <= b:
                        raise AnalyticalDomainError('A power reaches an undefined point.')
                    values = [self._power(a, exponent), self._power(b, exponent)]
                    if exponent > 0 and a <= 0 <= b:
                        values.append(0.0)
                    result = min(values), max(values)
                else:
                    if a < 0 or (a == 0 and c <= 0):
                        raise AnalyticalDomainError('The fractional power leaves its real domain.')
                    values = [self._power(base, exponent) for base in (a, b) for exponent in (c, d)]
                    result = min(values), max(values)
        else:
            name = node.func.id
            a, b = self.interval(x0, x1, node.args[0], resolve)
            if name in ('sin', 'cos', 'tan'):
                if resolve and b - a > .16:
                    raise _AnalyticalRefine()
                if name == 'tan':
                    first = math.ceil((a - math.pi / 2) / math.pi - 1e-12)
                    if math.pi / 2 + first * math.pi <= b + 1e-12:
                        raise AnalyticalDomainError('A tangent pole ends this branch.')
                    result = math.tan(a), math.tan(b)
                elif b - a >= math.tau:
                    result = -1.0, 1.0
                else:
                    fn = math.sin if name == 'sin' else math.cos
                    values = [fn(a), fn(b)]
                    offset = math.pi / 2 if name == 'sin' else 0
                    for k in range(math.ceil((a - offset) / math.pi), math.floor((b - offset) / math.pi) + 1):
                        values.append(fn(offset + k * math.pi))
                    result = min(values), max(values)
            elif name == 'abs':
                result = (0.0 if a <= 0 <= b else min(abs(a), abs(b))), max(abs(a), abs(b))
            elif name in ('floor', 'roof'):
                fn = self.FUNCTIONS[name]
                if fn(a) != fn(b):
                    raise AnalyticalDomainError('An integer step breaks this continuous path.')
                result = float(fn(a)), float(fn(b))
            else:
                if ((name == 'sqrt' and a < 0) or (name == 'ln' and a <= 0)
                        or (name in ('arcsin', 'arccos') and (a < -1 or b > 1))):
                    raise AnalyticalDomainError('The curve reaches the end of its real domain.')
                try:
                    values = [self.FUNCTIONS[name](a), self.FUNCTIONS[name](b)]
                    if name == 'cosh' and a <= 0 <= b:
                        values.append(1.0)
                    result = min(values), max(values)
                except (ValueError, OverflowError):
                    raise AnalyticalDomainError('The function exceeds its real numeric domain.') from None
        return self._finite(result[0]), self._finite(result[1])

    def check_bandwidth(self, xmax, xmin=0.0):
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Call) and node.func.id in ('sin', 'cos', 'tan'):
                try:
                    lo, hi = self.interval(min(xmin, xmax), max(xmin, xmax), node.args[0])
                except AnalyticalDomainError:
                    continue
                if hi - lo > ANALYTICAL_MAX_PHASE:
                    raise AnalyticalExpressionError('Too much oscillation for a playable path. Reduce the frequency; sin(60x) is supported.')


class AnalyticalCurveBuilder:
    """Incremental adaptive graph construction, with bounded work per tick."""
    def __init__(self, expression, origin, radius=BALL_RADIUS, direction=1):
        self.expression = expression
        self.origin = V(*origin)
        self.direction = -1 if direction < 0 else 1
        margin = radius + 8.5
        self.bounds = LEFT + margin, TOP + margin, RIGHT - margin, BOTTOM - margin
        distance = self.bounds[2] - self.origin.x if self.direction > 0 else self.origin.x - self.bounds[0]
        self.xmax = max(0.0, distance / ANALYTICAL_UNIT)
        try:
            self.zero = expression.value(0.0)
        except AnalyticalDomainError:
            raise AnalyticalExpressionError('f(0) is undefined. Edit the expression so the curve can start at the ball.') from None
        expression.check_bandwidth(self.xmax * self.direction)
        if self.xmax <= 1e-7:
            raise AnalyticalExpressionError('There is no room in this direction. Choose the other side.')
        self.points = [self.origin]
        self.lengths = [0.0]
        self.length = 0.0
        self.evaluations = 0
        self.finished = self.stopped = False
        self.error = None
        self.reason = 'RIGHT WALL' if self.direction > 0 else 'LEFT WALL'
        self._cache = {0.0: self.origin}
        self._iterator = self._build()

    def _point(self, x):
        if x not in self._cache:
            self.evaluations += 1
            if self.evaluations > ANALYTICAL_MAX_EVALUATIONS:
                raise AnalyticalExpressionError('This curve needs too much detail. Simplify it or reduce its frequency.')
            signed_x = x * self.direction
            y = self.expression.value(signed_x)
            self._cache[x] = V(self.origin.x + signed_x * ANALYTICAL_UNIT,
                               self.origin.y - (y - self.zero) * ANALYTICAL_UNIT)
        return self._cache[x]

    def _inside(self, point):
        x0, y0, x1, y1 = self.bounds
        return x0 - 1e-7 <= point.x <= x1 + 1e-7 and y0 - 1e-7 <= point.y <= y1 + 1e-7

    def _append(self, point):
        previous = self.points[-1]
        if not self._inside(point):
            fraction, reason = 1.0, 'RIGHT WALL'
            for coordinate, delta, lo, hi, low_name, high_name in (
                    (previous.x, point.x - previous.x, self.bounds[0], self.bounds[2], 'LEFT WALL', 'RIGHT WALL'),
                    (previous.y, point.y - previous.y, self.bounds[1], self.bounds[3], 'CEILING', 'FLOOR')):
                if delta > 0 and coordinate + delta > hi:
                    value = (hi - coordinate) / delta
                    if value <= fraction:
                        fraction, reason = value, high_name
                elif delta < 0 and coordinate + delta < lo:
                    value = (lo - coordinate) / delta
                    if value <= fraction:
                        fraction, reason = value, low_name
            point = previous + (point - previous) * clamp(fraction, 0, 1)
            self.stopped, self.reason = True, reason
        distance = (point - previous).length
        if distance > 1e-8:
            self.points.append(point)
            self.length += distance
            self.lengths.append(self.length)
            if len(self.points) > ANALYTICAL_MAX_POINTS:
                raise AnalyticalExpressionError('Too many curve segments. Reduce the frequency or simplify the formula.')

    def _trace(self, left, right, depth=0):
        if self.stopped:
            return
        # One yield per refinement keeps even pathological input cooperative.
        yield None
        middle = (left + right) * .5
        domain = None
        refine = False
        try:
            self.evaluations += 1
            if self.evaluations > ANALYTICAL_MAX_EVALUATIONS:
                raise AnalyticalExpressionError('This expression exceeds the curve-detail budget. Please simplify it.')
            x0, x1 = sorted((left * self.direction, right * self.direction))
            low, high = self.expression.interval(x0, x1, resolve=True)
            a, m, b = self._point(left), self._point(middle), self._point(right)
            chord = (a + b) * .5
            interval_top = self.origin.y - (high - self.zero) * ANALYTICAL_UNIT
            interval_bottom = self.origin.y - (low - self.zero) * ANALYTICAL_UNIT
            # An interval bound can expose a narrow peak that neither endpoint
            # nor midpoint sees. Resolve it before drawing any connecting chord.
            hidden_feature = (interval_top < min(a.y, m.y, b.y) - .24
                              or interval_bottom > max(a.y, m.y, b.y) + .24)
            refine = ((m - chord).length > .24 or (b - a).length > 8.0
                      or hidden_feature
                      or (self._inside(a) and self._inside(b) and not self._inside(m)))
        except _AnalyticalRefine:
            refine = True
        except AnalyticalDomainError as error:
            refine, domain = True, error
        if refine:
            if depth >= 24 or right - left < 1e-9:
                if domain:
                    self.stopped = True
                    self.reason = 'DOMAIN END / DISCONTINUITY'
                    return
                raise AnalyticalExpressionError('The curve changes too quickly here. Reduce its frequency or steepness.')
            yield from self._trace(left, middle, depth + 1)
            if not self.stopped:
                yield from self._trace(middle, right, depth + 1)
        else:
            self._append(b)

    def _build(self):
        left = 0.0
        while left < self.xmax - 1e-12 and not self.stopped:
            right = min(self.xmax, left + .04)
            yield from self._trace(left, right)
            left = right
        if self.length < .05 or len(self.points) < 2:
            side = 'rightward' if self.direction > 0 else 'leftward'
            raise AnalyticalExpressionError(f'There is no continuous {side} branch at x=0. Edit the expression or change direction.')

    def advance(self, budget=96):
        if self.finished:
            return True
        try:
            for _ in range(budget):
                next(self._iterator)
        except StopIteration:
            self.finished = True
        except AnalyticalExpressionError as error:
            self.error, self.finished = str(error), True
        return self.finished

    def run(self):
        while not self.advance(2048):
            pass
        if self.error:
            raise AnalyticalExpressionError(self.error)
        return self


def analytical_panel_rect(world):
    return pygame.Rect(round(LEFT * DRAW_SCALE + 18),
                       round(BOTTOM * DRAW_SCALE - 166), 760, 148)


def analytical_direction_rects(world):
    panel = analytical_panel_rect(world)
    return {-1: pygame.Rect(panel.x + 280, panel.y + 9, 106, 24),
             1: pygame.Rect(panel.x + 394, panel.y + 9, 106, 24)}


class AnalyticalMixin:
    def init_analytical(self):
        self.analytical_collector = None
        self.analytical_origin = V(0, 0)
        self.analytical_phase = 'off'
        self.analytical_age = 0.0
        self.analytical_phase_age = 0.0
        self.analytical_expression = 'sin(x)'
        self.analytical_caret = len(self.analytical_expression)
        self.analytical_select_all = True
        self.analytical_error = ''
        self.analytical_curve = None
        self.analytical_distance = 0.0
        self.analytical_segment = 1
        self.analytical_fade = 0.0
        self.analytical_saved_velocity = V(0, 0)
        self.analytical_saved_angular_velocity = 0.0
        self.analytical_completed = False
        self.analytical_direction = 1
        self.analytical_phantoms = []
        self.analytical_phantom_hits = {}

    def start_analytical(self, collector=None):
        collector = collector or self.balls[0]
        self.init_analytical()
        self.analytical_collector = collector
        self.analytical_origin = V(*collector.body.position)
        self.analytical_direction = -1 if self.analytical_origin.x > (LEFT + RIGHT) * .5 else 1
        self.spawn_analytical_phantoms()
        self.analytical_saved_velocity = V(*collector.body.velocity)
        self.analytical_saved_angular_velocity = collector.body.angular_velocity
        self.analytical_phase = 'axes'
        self.active_left = 0.0
        collector.body.velocity = (0, 0)
        collector.body.angular_velocity = 0
        collector.body.force = (0, 0)
        collector.previous = V(*collector.body.position)
        collector.trail.clear()
        if collector.body.space is self.space:
            self.space.remove(collector.shape, collector.body)
        self.wall_impacts.discard(collector)
        self.paddle_impacts.discard(collector)
        self.wave_contacts.pop(collector, None)
        self.burst(collector.body.position, ANALYTICAL_COLOR, 28)

    def spawn_analytical_phantoms(self):
        """Four fixed, temporary targets on the roomier side of the origin."""
        margin = TARGET_RADIUS + 36
        origin = self.analytical_origin
        if self.analytical_direction < 0:
            lo, hi = LEFT + margin, origin.x - max(margin, BALL_RADIUS + TARGET_RADIUS + 25)
        else:
            lo, hi = origin.x + max(margin, BALL_RADIUS + TARGET_RADIUS + 25), RIGHT - margin
        top, bottom = TOP + margin, BOTTOM - margin - 70
        self.analytical_phantoms = []
        self.analytical_phantom_hits = {}
        # Stratified x bands keep all four discoverable and prevent clustering.
        for index in range(ANALYTICAL_PHANTOM_COUNT):
            band0 = lo + (hi - lo) * index / ANALYTICAL_PHANTOM_COUNT
            band1 = lo + (hi - lo) * (index + 1) / ANALYTICAL_PHANTOM_COUNT
            chosen = None
            for _ in range(48):
                p = V(self.rng.uniform(band0, band1), self.rng.uniform(top, bottom))
                if ((p - self.target).length > TARGET_RADIUS * 2 + 26
                        and all((p - other).length > TARGET_RADIUS * 2 + 26 for other in self.analytical_phantoms)
                        and self.paddle_shape.point_query(p).distance > TARGET_RADIUS + 12):
                    chosen = p
                    break
            if chosen is None:
                # Bounded fallback still remains in its side and x band.
                candidates = [V((band0 + band1) * .5, top + (bottom - top) * k / 16) for k in range(17)]
                chosen = max(candidates, key=lambda p: min((p - q).length for q in [self.target, *self.analytical_phantoms]))
            self.analytical_phantoms.append(chosen)
            self.burst(chosen, ANALYTICAL_ACCENT, 10)

    def analytical_targets(self):
        if self.active != 'analytical':
            return []
        return [(index + 1, position) for index, position in enumerate(self.analytical_phantoms)
                if index + 1 not in self.analytical_phantom_hits]

    def analytical_target_ready(self, index):
        return (self.active == 'analytical' and 1 <= index <= len(self.analytical_phantoms)
                and index not in self.analytical_phantom_hits)

    def award_analytical_target(self, index):
        if not self.analytical_target_ready(index):
            return False
        self.analytical_phantom_hits[index] = self.analytical_age
        self.score += 1
        self.burst(self.analytical_phantoms[index - 1], (255, 114, 154), 28)
        return True

    def submit_analytical(self, expression=None):
        if self.active != 'analytical' or self.analytical_phase not in ('axes', 'edit'):
            return False
        if expression is not None:
            self.analytical_expression = expression[:ANALYTICAL_INPUT_LIMIT]
            self.analytical_caret = len(self.analytical_expression)
        try:
            parsed = AnalyticalExpression(self.analytical_expression)
            self.analytical_curve = AnalyticalCurveBuilder(parsed, self.analytical_origin,
                                                           self.analytical_collector.radius,
                                                           self.analytical_direction)
        except AnalyticalExpressionError as error:
            self.analytical_error = str(error)
            self.analytical_phase = 'edit'
            return False
        self.analytical_error = ''
        self.analytical_phase = 'calculate'
        self.analytical_phase_age = 0.0
        self.analytical_select_all = False
        return True

    def handle_analytical_event(self, event, position=None):
        if self.active != 'analytical' or self.analytical_phase not in ('axes', 'edit'):
            return False
        if event.type == pygame.TEXTINPUT:
            text = ''.join(character for character in event.text if character.isprintable())
            if self.analytical_select_all:
                self.analytical_expression, self.analytical_caret = '', 0
                self.analytical_select_all = False
            room = ANALYTICAL_INPUT_LIMIT - len(self.analytical_expression)
            value = self.analytical_expression
            index = self.analytical_caret
            self.analytical_expression = value[:index] + text[:room] + value[index:]
            self.analytical_caret += len(text[:room])
            self.analytical_error = ''
            return True
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return False
            modifiers = getattr(event, 'mod', 0)
            if modifiers & pygame.KMOD_CTRL and event.key == pygame.K_p:
                return False
            value, index = self.analytical_expression, self.analytical_caret
            if modifiers & pygame.KMOD_CTRL and event.key == pygame.K_a:
                self.analytical_select_all = True
            elif modifiers & pygame.KMOD_CTRL and event.key == pygame.K_v:
                try:
                    if not pygame.scrap.get_init():
                        pygame.scrap.init()
                    pasted = pygame.scrap.get(pygame.SCRAP_TEXT)
                    if pasted:
                        text = pasted.decode('utf-8', errors='replace').split('\x00', 1)[0]
                        self.handle_analytical_event(pygame.event.Event(pygame.TEXTINPUT, text=text))
                except (pygame.error, UnicodeError):
                    self.analytical_error = 'Clipboard unavailable. Type the expression in the field.'
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.submit_analytical()
            elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                if self.analytical_select_all:
                    value, index = '', 0
                elif event.key == pygame.K_BACKSPACE and index > 0:
                    value, index = value[:index - 1] + value[index:], index - 1
                elif event.key == pygame.K_DELETE:
                    value = value[:index] + value[index + 1:]
                self.analytical_select_all = False
                self.analytical_expression, self.analytical_caret = value, index
                self.analytical_error = ''
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_HOME, pygame.K_END):
                if event.key == pygame.K_HOME:
                    index = 0
                elif event.key == pygame.K_END:
                    index = len(value)
                elif self.analytical_select_all:
                    index = 0 if event.key == pygame.K_LEFT else len(value)
                else:
                    index = clamp(index + (1 if event.key == pygame.K_RIGHT else -1), 0, len(value))
                self.analytical_caret, self.analytical_select_all = int(index), False
            # Consume printable game shortcut keys; TEXTINPUT inserts the text.
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            position = event.pos if position is None else position
            panel = analytical_panel_rect(self)
            if panel.collidepoint(position):
                for direction, rectangle in analytical_direction_rects(self).items():
                    if rectangle.collidepoint(position):
                        self.analytical_direction = direction
                        self.analytical_error = ''
                        return True
                if pygame.Rect(panel.x + 638, panel.y + 36, 104, 40).collidepoint(position):
                    self.submit_analytical()
                return True
        return False

    def step_analytical(self, dt, hit_targets=None):
        if self.active != 'analytical':
            self.analytical_fade = max(0.0, self.analytical_fade - dt)
            return
        self.analytical_age += dt
        self.analytical_phase_age += dt
        ball = self.analytical_collector
        if ball is None or ball not in self.balls:
            self.finish_powerup()
            return
        phase = self.analytical_phase
        if phase == 'axes':
            if self.analytical_phase_age >= .7:
                self.analytical_phase, self.analytical_phase_age = 'edit', 0.0
        elif phase == 'calculate':
            curve = self.analytical_curve
            if curve.advance():
                if curve.error:
                    self.analytical_error = curve.error
                    self.analytical_curve = None
                    self.analytical_phase = 'edit'
                else:
                    self.analytical_phase = 'plot'
                self.analytical_phase_age = 0.0
        elif phase == 'plot':
            if self.analytical_phase_age >= .85:
                self.analytical_phase, self.analytical_phase_age = 'travel', 0.0
                self.burst(ball.body.position, ANALYTICAL_ACCENT, 18)
        elif phase == 'travel':
            curve = self.analytical_curve
            duration = clamp(curve.length / 750, .65, 8.0)
            distance = min(curve.length, self.analytical_distance + curve.length / duration * dt)
            previous = V(*ball.body.position)
            hits = {} if hit_targets is None else hit_targets
            while self.analytical_distance < distance - 1e-10 and self.analytical_segment < len(curve.points):
                index = self.analytical_segment
                stop = min(distance, curve.lengths[index])
                length = curve.lengths[index] - curve.lengths[index - 1]
                fraction = clamp((stop - curve.lengths[index - 1]) / max(1e-12, length), 0, 1)
                position = curve.points[index - 1] + (curve.points[index] - curve.points[index - 1]) * fraction
                for target_index, target in self.active_targets():
                    if (target_index not in hits and self.target_ready(target_index)
                            and swept_circle(previous, position, target, ball.radius + TARGET_RADIUS)):
                        hits[target_index] = ball
                ball.body.position = position
                previous = position
                self.analytical_distance = stop
                if stop >= curve.lengths[index] - 1e-10:
                    self.analytical_segment += 1
            if hit_targets is None:
                for target_index, collector in hits.items():
                    self.award_target(collector, target_index=target_index)
            if distance >= curve.length - 1e-8:
                self.analytical_completed = True
                # World awards its accumulated swept hits after this method.
                self.analytical_phase, self.analytical_phase_age = 'release', 0.0
        elif phase == 'release' and hit_targets is None:
            self.finish_powerup()

    def finish_analytical(self):
        ball = self.analytical_collector
        if ball is not None and ball in self.balls:
            velocity = self.analytical_saved_velocity
            curve = self.analytical_curve
            if self.analytical_completed and curve is not None and len(curve.points) > 1:
                tangent = (curve.points[-1] - curve.points[-2]).normalized()
                velocity = tangent * clamp(velocity.length, 380, 900)
            ball.body.position = self.fit_to_solids(ball.body.position, ball.radius)
            ball.body.velocity = velocity
            ball.body.angular_velocity = self.analytical_saved_angular_velocity
            ball.body.force = (0, 0)
            ball.previous = V(*ball.body.position)
            ball.trail.clear()
            if ball.body.space is not self.space:
                self.space.add(ball.body, ball.shape)
            self.by_body[ball.body] = ball
            ball.body.activate()
            self.burst(ball.body.position, ANALYTICAL_COLOR, 25)
        self.analytical_collector = None
        for index, position in enumerate(self.analytical_phantoms, 1):
            if index not in self.analytical_phantom_hits:
                self.burst(position, ANALYTICAL_ACCENT, 8)
        self.analytical_phantoms = []
        self.analytical_phantom_hits = {}
        self.analytical_phase = 'off'
        self.analytical_fade = .65


class AnalyticalRendererMixin:
    def draw_analytical_background(self, world):
        active = world.active == 'analytical'
        if not active and world.analytical_fade <= 0:
            return
        origin = world.analytical_origin * DRAW_SCALE
        fade = 1.0 if active else world.analytical_fade / .65
        progress = min(1.0, world.analytical_age / .7)
        progress = 1 - (1 - progress) ** 3
        layer = getattr(self, '_analytical_grid_layer', None)
        if layer is None:
            layer = self._analytical_grid_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        layer.fill((0, 0, 0, 0))
        left, top, right, bottom = (value * DRAW_SCALE for value in (LEFT + 9, TOP + 9, RIGHT - 9, BOTTOM - 9))
        x0, x1 = origin.x + (left - origin.x) * progress, origin.x + (right - origin.x) * progress
        y0, y1 = origin.y + (top - origin.y) * progress, origin.y + (bottom - origin.y) * progress
        unit = ANALYTICAL_UNIT * DRAW_SCALE
        for index in range(math.ceil((x0 - origin.x) / unit), math.floor((x1 - origin.x) / unit) + 1):
            x = origin.x + index * unit
            pygame.draw.line(layer, (*ANALYTICAL_COLOR, round((58 if index == 0 else 18) * fade)), (x, y0), (x, y1))
            if index and index % 2 == 0 and y0 + 16 < origin.y < y1 - 16:
                label = self.text(str(index), 14, self.shade(ANALYTICAL_COLOR, .45 * fade))
                layer.blit(label, (x + 4, origin.y + 5))
        for index in range(math.ceil((origin.y - y1) / unit), math.floor((origin.y - y0) / unit) + 1):
            y = origin.y - index * unit
            pygame.draw.line(layer, (*ANALYTICAL_COLOR, round((72 if index == 0 else 18) * fade)), (x0, y), (x1, y))
            if index and index % 2 == 0 and x0 + 18 < origin.x < x1 - 18:
                label = self.text(str(index), 14, self.shade(ANALYTICAL_COLOR, .45 * fade))
                layer.blit(label, (origin.x + 6, y + 3))
        if progress > .9:
            pygame.draw.polygon(layer, (*ANALYTICAL_COLOR, round(115 * fade)), ((x1, origin.y), (x1 - 8, origin.y - 4), (x1 - 8, origin.y + 4)))
            pygame.draw.polygon(layer, (*ANALYTICAL_COLOR, round(115 * fade)), ((origin.x, y0), (origin.x - 4, y0 + 8), (origin.x + 4, y0 + 8)))
            layer.blit(self.text('x', 16, self.shade(ANALYTICAL_COLOR, .65 * fade)), (x1 - 15, origin.y + 9))
            layer.blit(self.text('y', 16, self.shade(ANALYTICAL_COLOR, .65 * fade)), (origin.x + 10, y0 + 4))
            layer.blit(self.text('(0,0)', 14, self.shade(ANALYTICAL_COLOR, .65 * fade)), (origin.x + 15, origin.y + 15))
        self.canvas.blit(layer, (0, 0))
        curve = world.analytical_curve
        if curve is not None and len(curve.points) > 1 and not curve.error:
            if world.analytical_phase == 'calculate':
                visible = 0
            elif world.analytical_phase == 'plot':
                visible = max(1, round((len(curve.points) - 1) * min(1.0, world.analytical_phase_age / .85)))
            else:
                visible = len(curve.points) - 1
            key = (id(world), id(curve))
            if getattr(self, '_analytical_curve_key', None) != key:
                self._analytical_curve_key = key
                self._analytical_curve_layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                self._analytical_curve_drawn = 0
            if visible > self._analytical_curve_drawn:
                start = self._analytical_curve_drawn
                points = [point * DRAW_SCALE for point in curve.points[start:visible + 1]]
                if len(points) > 1:
                    pygame.draw.lines(self._analytical_curve_layer, (*ANALYTICAL_ACCENT, 28), False, points, 5)
                    pygame.draw.lines(self._analytical_curve_layer, (*ANALYTICAL_COLOR, 105), False, points, 2)
                    pygame.draw.aalines(self._analytical_curve_layer, (*INK, 195), False, points)
                self._analytical_curve_drawn = visible
            self._analytical_curve_layer.set_alpha(round(255 * fade))
            self.canvas.blit(self._analytical_curve_layer, (0, 0))
            if visible > 0:
                endpoint = curve.points[visible] * DRAW_SCALE
                self.halo(endpoint, self.shade(ANALYTICAL_COLOR, fade), 19)
                pygame.draw.circle(self.canvas, self.shade(INK, fade), endpoint, 3)
        if active and world.analytical_phase != 'travel':
            for index in range(4):
                angle = world.analytical_age * 1.8 + index * math.pi / 2
                point = origin + V(math.cos(angle), math.sin(angle)) * (25 + math.sin(world.analytical_age * 3) * 3)
                pygame.draw.circle(self.canvas, ANALYTICAL_COLOR if index % 2 else ANALYTICAL_ACCENT, point, 2)
            pygame.draw.circle(self.canvas, self.shade(ANALYTICAL_COLOR, .5), origin, 18, 1)

    def draw_analytical_phantoms(self, world):
        if world.active != 'analytical':
            return
        for index, position in enumerate(world.analytical_phantoms, 1):
            p = self.project(position)
            hit_at = world.analytical_phantom_hits.get(index)
            age = world.analytical_age - hit_at if hit_at is not None else 0.0
            if hit_at is not None and age > .65:
                continue
            appear = clamp((world.analytical_age - index * .06) / .4, 0, 1)
            strength = appear * (1 - age / .65) if hit_at is not None else appear
            color = (255, 100, 140) if hit_at is not None else ANALYTICAL_ACCENT
            r = TARGET_RADIUS * DRAW_SCALE * (appear + age * 1.6)
            self.halo(p, self.shade(color, strength * .8), max(1, round(r * 2.3)))
            for ring in range(2):
                radius = r + ring * 5
                phase = world.sim_time * (.6 if ring else -.8) + index
                for part in range(4):
                    points = [p + V(math.cos(a), math.sin(a)) * radius
                              for a in (phase + part * math.pi / 2 + k * .10 for k in range(11))]
                    pygame.draw.aalines(self.canvas, self.shade(color, strength * (.8 - ring * .3)), False, points)
            diamond = [p + V(math.cos(a), math.sin(a)) * r * .57
                       for a in (world.sim_time * .45 + k * math.pi / 2 for k in range(4))]
            pygame.draw.aalines(self.canvas, self.shade(INK, strength * .65), True, diamond)
            pygame.draw.circle(self.canvas, self.shade(color, strength), p, max(1, round(3 * appear)))

    def draw_analytical_overlay(self, world, mouse=None):
        if world.active != 'analytical':
            return
        panel = analytical_panel_rect(world)
        phase = world.analytical_phase
        if phase == 'axes':
            self.label('MAPPING LOCAL COORDINATES', (WIDTH // 2, TOP * DRAW_SCALE + 25), 18,
                       self.shade(ANALYTICAL_COLOR, .65), True)
        elif phase in ('edit', 'calculate'):
            # Fade the complete editor, including text, over the live arena.
            # Reuse only panel-sized surfaces; the grid and targets stay crisp.
            if not hasattr(self, '_analytical_panel_back'):
                self._analytical_panel_back = pygame.Surface(panel.size)
                self._analytical_panel_front = pygame.Surface(panel.size)
            self._analytical_panel_back.blit(self.canvas, (0, 0), panel)
            pygame.draw.rect(self.canvas, (12, 24, 41), panel, border_radius=10)
            pygame.draw.rect(self.canvas, self.shade(ANALYTICAL_COLOR, .48), panel, 1, border_radius=10)
            self.label('ANALYTICAL PATH', (panel.x + 18, panel.y + 11), 16, ANALYTICAL_COLOR)
            self.label('RADIANS / 50 PX', (panel.right - 176, panel.y + 13), 14, MUTED)
            for direction, rectangle in analytical_direction_rects(world).items():
                selected = direction == world.analytical_direction
                pygame.draw.rect(self.canvas, (33, 72, 89) if selected else (19, 36, 53), rectangle, border_radius=5)
                pygame.draw.rect(self.canvas, ANALYTICAL_COLOR if selected else MUTED, rectangle, 1, border_radius=5)
                self.label('x < 0  LEFT' if direction < 0 else 'x > 0 RIGHT', rectangle.center, 14,
                           INK if selected else MUTED, True)
            self.label('f(x) =', (panel.x + 18, panel.y + 46), 20, INK)
            field = pygame.Rect(panel.x + 98, panel.y + 36, 528, 40)
            pygame.draw.rect(self.canvas, (6, 15, 29), field, border_radius=6)
            pygame.draw.rect(self.canvas, self.shade(ANALYTICAL_COLOR, .7), field, 1, border_radius=6)
            value, index = world.analytical_expression, world.analytical_caret
            font = self.fonts.get(20)
            start = 0
            while start < index and font.size(value[start:index])[0] > field.width - 24:
                start += 1
            old_clip = self.canvas.get_clip()
            self.canvas.set_clip(field.inflate(-12, -4).clip(old_clip))
            if world.analytical_select_all:
                pygame.draw.rect(self.canvas, (35, 65, 91), (field.x + 8, field.y + 7,
                                                          font.size(value[start:])[0], 26))
            self.label(value[start:], (field.x + 9, field.y + 10), 20, INK)
            if phase != 'calculate' and int(world.analytical_age * 2) % 2 == 0:
                x = field.x + 9 + font.size(value[start:index])[0]
                pygame.draw.line(self.canvas, ANALYTICAL_COLOR, (x, field.y + 8), (x, field.bottom - 8), 1)
            self.canvas.set_clip(old_clip)
            launch = pygame.Rect(panel.x + 638, panel.y + 36, 104, 40)
            pygame.draw.rect(self.canvas, (32, 69, 87), launch, border_radius=6)
            self.label('BUILDING' if phase == 'calculate' else 'ENTER >', launch.center, 16, ANALYTICAL_COLOR, True)
            if world.analytical_error:
                error = world.analytical_error
                words, line, lines = error.split(), '', []
                for word in words:
                    if len(line) + len(word) > 89:
                        lines.append(line)
                        line = ''
                    line += (' ' if line else '') + word
                lines.append(line)
                for row, text in enumerate(lines[:2]):
                    self.label(text, (panel.x + 18, panel.y + 85 + row * 18), 14, (255, 151, 158))
            else:
                self.label('sqrt sin cos tan ln abs floor roof sinh cosh tanh arcsin arccos arctan',
                           (panel.x + 18, panel.y + 85), 14, MUTED)
                self.label('x  e  pi  phi    + - * / ^    ()    Shifted by -f(0).  Ctrl+A: all  Ctrl+V: paste',
                           (panel.x + 18, panel.y + 104), 14, MUTED)
            self.label('Hover to reveal the editor. Choose a direction before launching.',
                       (panel.x + 18, panel.y + 126), 12, self.shade(ANALYTICAL_COLOR, .7))
            self._analytical_panel_front.blit(self.canvas, (0, 0), panel)
            self._analytical_panel_front.set_alpha(255 if mouse is not None and panel.collidepoint(mouse) else 40)
            self.canvas.blit(self._analytical_panel_back, panel)
            self.canvas.blit(self._analytical_panel_front, panel)
        elif phase in ('plot', 'travel'):
            label = 'TRACING THE FUNCTION' if phase == 'plot' else 'RIDING THE CURVE'
            self.label(label, (WIDTH // 2, TOP * DRAW_SCALE + 25), 18, ANALYTICAL_COLOR, True)
            expression = world.analytical_expression
            if len(expression) > 62:
                expression = expression[:59] + '...'
            self.label(f'y = {expression} - f(0)', (WIDTH // 2, TOP * DRAW_SCALE + 48), 14, MUTED, True)
            if world.analytical_curve is not None:
                self.label('ENDS AT ' + world.analytical_curve.reason,
                           (WIDTH // 2, TOP * DRAW_SCALE + 67), 14,
                           self.shade(ANALYTICAL_ACCENT, .72), True)


class World(AnalyticalMixin, GaussianMixin, DroneMixin, QuantumMixin, PortalTimeMixin, VoronoiMixin, WormholeMixin, SnellMixin):
    """Toda la logica usa segundos simulados; no consulta reloj, raton ni pantalla."""
    def __init__(self, seed=None, effects=True):
        self.rng = random.Random(seed)
        # Los efectos graficos no consumen aleatoriedad de la partida.
        self.fx_rng = random.Random(None if seed is None else seed + 991)
        self.effects = effects
        self.space = pymunk.Space()
        self.space.gravity = (0, GRAVITY)
        self.space.iterations = 20
        self.space.collision_slop = 0.1
        self.walls = []
        for a, b in (((LEFT, TOP), (RIGHT, TOP)), ((RIGHT, TOP), (RIGHT, BOTTOM)),
                     ((RIGHT, BOTTOM), (LEFT, BOTTOM)), ((LEFT, BOTTOM), (LEFT, TOP))):
            wall = pymunk.Segment(self.space.static_body, a, b, 8.0)
            wall.elasticity, wall.friction = WALL_ELASTICITY, 0.0
            wall.collision_type = 2
            self.space.add(wall)
            self.walls.append(wall)
        self.paddle = pymunk.Body(body_type=pymunk.Body.KINEMATIC)
        self.paddle.position = (SCREEN_WIDTH / 2, PADDLE_Y)
        self.paddle_shape = pymunk.Poly(self.paddle, PADDLE_VERTICES, radius=0.5)
        self.paddle_shape.elasticity, self.paddle_shape.friction = 0.96, 0.0
        self.paddle_shape.collision_type = 3
        self.space.add(self.paddle, self.paddle_shape)
        self.by_body = {}
        self.wall_impacts = set()
        self.paddle_impacts = set()
        self.wave_contacts = {}
        self.space.on_collision(1, 2, pre_solve=self.wall_pre_solve, post_solve=self.wall_post_solve)
        self.space.on_collision(1, 3, pre_solve=self.paddle_pre_solve, post_solve=self.paddle_post_solve)
        self.space.on_collision(1, 1, post_solve=self.record_wave_contact)
        self.previous_paddle = self.paddle.position
        self.previous_angle = 0.0
        self.hspeed, self.aspeed = 5, 5
        self.ball_color, self.target_color = 0, 1
        self.target_style = 0
        self.trail_style = 0
        self.secret_unlocked = False
        self.discovered = set()
        self.skip_ready_at = 0.0
        self.score_multiplier = 1
        self.fortune_reveal_left = 0.0
        self.score, self.hits, self.sim_time = 0, 0, 0.0
        self.balls = []
        self.target = V(SCREEN_WIDTH / 2, 250)
        self.target_lock = 0.0
        self.pickup = None
        self.active = None
        self.active_left = 0.0
        self.explosion_carrier = None
        self.exploded = False
        self.projectiles = []
        self.init_portal_time()
        self.init_voronoi()
        self.init_wormhole()
        self.init_snell()
        self.init_quantum()
        self.init_gaussian()
        self.init_drone()
        self.init_analytical()
        self.snell_target_locks = [0.0, 0.0]
        self.fission_originals = {}
        self.fusion_progress = None
        self.fusion_centers = {}
        self.fusion_starts = {}
        self.fusion_velocities = {}
        self.pending_balls = 0
        self.spawn_left = self.next_wait()
        self.particles, self.rings = [], []
        self.message, self.message_left = "REACH THE TARGET", 3.0
        self._trail_clock = 0.0
        self.safety_corrections = 0
        self.add_ball()
        self.target = self.free_position(TARGET_RADIUS + 12)

    def next_wait(self):
        return self.rng.expovariate(1.0 / POWER_MEAN_WAIT)

    def active_targets(self):
        if self.active == 'snell':
            return list(enumerate(self.snell_targets))
        return [(0, self.target)] + self.analytical_targets()

    def target_ready(self, index):
        if self.active == 'analytical' and index > 0:
            return self.analytical_target_ready(index)
        if self.active == 'snell':
            return self.snell_target_locks[index] <= 0
        return self.target_lock <= 0

    @property
    def speed_limit(self):
        if self.active == 'overdrive':
            return BOOST_MAX_SPEED
        return WAVE_MAX_SPEED if self.active == 'duality' else MAX_BALL_SPEED

    def wall_pre_solve(self, arbiter, space, data):
        self.record_drone_wall(arbiter)
        if self.active == "overdrive":
            # Un apoyo continuo no cuenta como rebote: evita que el ruido
            # numerico del suelo acelere una bola que estaba quieta.
            normal_speed = abs(arbiter.shapes[0].body.velocity.dot(arbiter.normal))
            arbiter.restitution = 1.0 if normal_speed >= TURBO_MIN_IMPACT else 0.0

    def wall_post_solve(self, arbiter, space, data):
        self.record_wave_contact(arbiter, space, data)
        if (self.active == "overdrive" and arbiter.is_first_contact
                and arbiter.restitution > 0 and arbiter.total_impulse.length_squared > 1):
            ball = self.by_body.get(arbiter.shapes[0].body)
            if ball is not None:
                self.wall_impacts.add(ball)

    def paddle_pre_solve(self, arbiter, space, data):
        self.record_quantum_pre(arbiter)
        ball = self.by_body.get(arbiter.shapes[0].body)
        if ball is not None and ball.body.position.y > BOTTOM - 70 and ball.body.velocity.length < 450:
            # La punta recoge suavemente las bolas del suelo; el resto golpea.
            arbiter.restitution = 0.04

    def paddle_post_solve(self, arbiter, space, data):
        self.record_quantum_post(arbiter)
        self.record_wave_contact(arbiter, space, data)
        if arbiter.is_first_contact and arbiter.total_impulse.length_squared > .01:
            ball = self.by_body.get(arbiter.shapes[0].body)
            if ball is not None and self.sim_time >= ball.split_ready_at:
                self.paddle_impacts.add(ball)

    def record_wave_contact(self, arbiter, space, data):
        # El apoyo continuo por gravedad no reinicia la onda: asi una pelota
        # quieta en el suelo aun completa su oscilacion de amplitud constante.
        if self.active != 'duality' or arbiter.total_impulse.length_squared < 1.0:
            return
        for index, shape in enumerate(arbiter.shapes):
            ball = self.by_body.get(shape.body)
            if ball is not None and ball.wave_active:
                other = arbiter.shapes[1 - index]
                normal = arbiter.normal * (-1 if index == 0 else 1)
                other_ball = self.by_body.get(other.body)
                if other_ball is not None and other_ball.wave_active:
                    # Los dos centros intercambian impulso, sin transferir la
                    # velocidad artificial de sus oscilaciones transversales.
                    surface = other_ball.wave_incoming_base
                    share = other.body.mass / (ball.body.mass + other.body.mass)
                else:
                    surface = other.body.velocity_at_world_point(ball.body.position)
                    share = 1.0
                self.wave_contacts.setdefault(ball, []).append(
                    (normal, surface, arbiter.restitution, share))

    def boost_ball(self, ball):
        ball.body.velocity *= 1.15
        ball.limit_speed(BOOST_MAX_SPEED)
        ball.wall_boost_count += 1

    def satellite_acceleration(self, position):
        delta = self.target - position
        distance2 = delta.length_squared
        if distance2 < 1e-12:
            return V(0, 0)
        # Potencial central suavizado: atraccion fuerte, sin singularidad ni
        # salto de aceleracion en el centro. Las entradas rapidas pueden escapar.
        acceleration = min(SATELLITE_MAX_ACCEL,
                           SATELLITE_STRENGTH * math.sqrt(distance2)
                           / (distance2 + SATELLITE_SOFT_RADIUS ** 2) ** 1.5)
        return delta * (acceleration / math.sqrt(distance2))

    def paddle_endpoints(self):
        d = V(math.cos(self.paddle.angle), math.sin(self.paddle.angle)) * PADDLE_HALF
        return self.paddle.position - d, self.paddle.position + d

    def safe_position(self, pos, radius, avoid_target=False, ignore=None):
        margin = radius + 9.0
        if not (LEFT + margin <= pos.x <= RIGHT - margin and TOP + margin <= pos.y <= BOTTOM - margin):
            return False
        if self.paddle_shape.point_query(pos).distance < radius + 3:
            return False
        if any(ball is not ignore and (pos - ball.body.position).length_squared < (radius + ball.radius + 3) ** 2 for ball in self.balls):
            return False
        if avoid_target and any((pos - target).length < radius + TARGET_RADIUS + 20
                                for _, target in self.active_targets()):
            return False
        if self.pickup and (pos - self.pickup.position).length < radius + PICKUP_RADIUS + 12:
            return False
        return True

    def free_position(self, radius, avoid_target=False, ignore=None):
        for _ in range(40):
            p = V(self.rng.uniform(LEFT + radius + 26, RIGHT - radius - 26),
                  self.rng.uniform(TOP + radius + 28, BOTTOM - 260 - radius))
            if self.safe_position(p, radius, avoid_target, ignore):
                return p
        # Busqueda determinista acotada si la zona aleatoria esta ocupada.
        spacing = max(28, int(radius * 2 + 4))
        for y in range(int(TOP + radius + 12), int(BOTTOM - 140 - radius), spacing):
            for x in range(int(LEFT + radius + 12), int(RIGHT - radius - 12), spacing):
                p = V(x, y)
                if self.safe_position(p, radius, avoid_target, ignore):
                    return p
        return None

    def add_ball(self, temporary=False):
        radius = GIANT_RADIUS if self.active == "giant" else BALL_RADIUS
        pos = self.free_position(radius, avoid_target=True)
        if pos is None:
            # Sin limite de cantidad: si el campo esta lleno, esperar un hueco.
            if not temporary:
                self.pending_balls += 1
            return None
        ball = Ball(self.space, pos, (self.rng.uniform(-260, 260), -380), radius, temporary)
        self.balls.append(ball)
        self.by_body[ball.body] = ball
        if self.active == 'duality':
            self.start_wave(ball)
        elif self.active == 'timewarp':
            self.refresh_ghost(ball)
        return ball

    def teleport(self, ball, position):
        ball.body.position = position
        ball.previous = V(*position)
        ball.trail.clear()
        self.space.reindex_shapes_for_body(ball.body)

    def skip_target(self):
        if self.sim_time + 1e-9 < self.skip_ready_at:
            return False
        if self.active == 'snell':
            for index in range(2):
                self.replace_snell_target(index)
            self.target = self.snell_targets[0]
            self.snell_target_locks = [.08, .08]
            self.score -= 1
            self.skip_ready_at = self.sim_time + 30.0
            return True
        pos = self.free_position(TARGET_RADIUS + 12)
        if pos is not None:
            self.score -= 1
            self.target = pos
            self.target_lock = 0.08
            if self.active == 'wormhole':
                self.on_target_changed_wormhole()
            self.skip_ready_at = self.sim_time + 30.0
            return True
        return False

    def activate_powerup(self, kind, collector=None):
        if self.active is not None or kind not in POWERUPS:
            return False
        origin = self.pickup.position if self.pickup else V(SCREEN_WIDTH / 2, SCREEN_HEIGHT / 2)
        self.pickup = None
        self.active, self.active_left = kind, 3.0 if kind == "explosion" else POWER_DURATION
        self.discovered.add(kind)
        if kind == "giant":
            # Reservar primero todo el espacio para no agrandar dentro de otra bola.
            for ball in self.balls:
                ball.resize(self.space, GIANT_RADIUS)
                ball.giant_goal_radius = GIANT_RADIUS
            for ball in self.balls:
                p, r = ball.body.position, ball.radius
                if not self.safe_position(p, r, ignore=ball):
                    pos = self.free_position(r, avoid_target=True, ignore=ball)
                    if pos is None:
                        # Campo extremadamente poblado: reducir esta bola hasta que quepa.
                        ball.resize(self.space, BALL_RADIUS)
                        pos = self.free_position(BALL_RADIUS, ignore=ball)
                    if pos is not None:
                        self.teleport(ball, pos)
        elif kind == "multiball":
            for _ in range(10):
                self.add_ball(temporary=True)
        elif kind == "overdrive":
            for ball in self.balls:
                ball.normal_speed = ball.body.velocity.length
        elif kind == 'double':
            self.score_multiplier = roll_fortune(self.rng)
            self.fortune_reveal_left = 4.0
        elif kind == "satellite":
            self.space.gravity = (0, 0)
        elif kind == "explosion":
            self.explosion_carrier = collector or self.balls[0]
            self.exploded = False
        elif kind == 'duality':
            for ball in self.balls:
                self.start_wave(ball)
        elif kind in ('mobius', 'timewarp'):
            self.start_portal_time(kind)
        elif kind == 'voronoi':
            self.start_voronoi(collector or self.balls[0])
        elif kind == 'wormhole':
            self.start_wormhole()
        elif kind == 'snell':
            self.start_snell()
            self.snell_target_locks = [.08, .08]
        elif kind == 'quantum':
            self.start_quantum(collector)
        elif kind == 'gaussian':
            self.start_gaussian(collector)
        elif kind == 'drone':
            self.start_drone(collector)
        elif kind == 'analytical':
            self.start_analytical(collector)
        label, _, color = POWERUPS[kind]
        self.message, self.message_left = label, 2.8
        self.burst(origin, color, 44)
        return True

    def finish_powerup(self):
        kind = self.active
        if kind is None:
            return
        if kind == 'fission' and self.fission_originals:
            if self.fusion_progress is None:
                self.begin_fusion()
            return
        if kind == "giant":
            for ball in self.balls:
                ball.resize(self.space, BALL_RADIUS)
                ball.giant_goal_radius = BALL_RADIUS
                ball.trail.clear()
                self.teleport(ball, self.fit_to_solids(ball.body.position, BALL_RADIUS))
        elif kind == "multiball":
            for ball in self.balls[:]:
                if ball.temporary:
                    self.burst(ball.body.position, POWERUPS[kind][2], 6)
                    self.space.remove(ball.shape, ball.body)
                    self.by_body.pop(ball.body, None)
                    self.balls.remove(ball)
        elif kind == "overdrive":
            for ball in self.balls:
                current = ball.body.velocity.length
                ball.body.velocity = ball.body.velocity * (min(ball.normal_speed, MAX_BALL_SPEED) / current) if current > 1e-9 else V(0, 0)
        elif kind == 'duality':
            for ball in self.balls:
                ball.body.velocity = ball.wave_velocity
                ball.wave_active = False
                ball.trail = deque(maxlen=32)
        elif kind in ('mobius', 'timewarp'):
            self.finish_portal_time(kind)
        elif kind == 'voronoi':
            self.finish_voronoi()
        elif kind == 'wormhole':
            self.finish_wormhole()
        elif kind == 'quantum':
            self.finish_quantum()
        elif kind == 'gaussian':
            self.finish_gaussian()
        elif kind == 'drone':
            self.finish_drone()
        elif kind == 'analytical':
            self.finish_analytical()
        elif kind == 'snell':
            self.finish_snell()
            self.snell_target_locks = [0.0, 0.0]
            self.target = self.free_position(TARGET_RADIUS + 12) or self.target
            self.target_lock = .08
        self.space.gravity = (0, GRAVITY)
        self.active, self.active_left = None, 0.0
        self.explosion_carrier = None
        self.exploded = False
        self.spawn_left = self.next_wait()
        self.score_multiplier = 1
        self.fortune_reveal_left = 0.0
        self.message, self.message_left = "POWERUP COMPLETE", 1.6
        if self.quantum_unobserved:
            self.message, self.message_left = 'QUANTUM UNCERTAINTY: TOUCH EITHER BALL', 3600.0

    def update_powerup(self, dt):
        if self.active is not None:
            if self.active == 'drone' and self.drone_waiting:
                return
            if self.active in ('voronoi', 'gaussian', 'analytical'):
                return
            if self.active == 'fission' and self.fusion_progress is not None:
                return
            if self.active == "explosion" and self.exploded:
                if not self.projectiles:
                    self.finish_powerup()
                return
            self.active_left = max(0.0, self.active_left - dt)
            if self.active_left <= 1e-9:
                if self.active == "explosion":
                    self.detonate()
                else:
                    self.finish_powerup()
        elif self.pickup is None and not self.quantum_unobserved:
            self.spawn_left -= dt
            if self.spawn_left <= 1e-9:
                kind = self.rng.choice(tuple(POWERUPS))
                pos = self.free_position(PICKUP_RADIUS + 8, True)
                if pos is not None:
                    self.pickup = Pickup(kind, pos)
                    self.message, self.message_left = "A STAR HAS APPEARED", 3.0
                    self.burst(pos, POWERUPS[kind][2], 14)
                else:
                    self.spawn_left = 1.0

    def detonate(self):
        origin = self.explosion_carrier.body.position
        self.explosion_carrier.body.velocity = (0, 0)
        self.exploded = True
        for i in range(48):
            angle = -math.pi / 2 + i * math.tau / 48
            velocity = V(math.cos(angle), math.sin(angle)) * 1150
            self.projectiles.append(Projectile(origin, velocity))
        self.burst(origin, POWERUPS['explosion'][2], 64)
        self.message, self.message_left = 'SUPERNOVA', 1.5

    def step_projectiles(self, dt, hit_targets=None):
        hit = False
        live = []
        for shot in self.projectiles:
            shot.previous = shot.position
            shot.position += shot.velocity * dt
            for index, target in self.active_targets():
                if self.target_ready(index) and swept_circle(shot.previous, shot.position, target, shot.radius + TARGET_RADIUS):
                    hit = True
                    if hit_targets is not None:
                        hit_targets.setdefault(index, None)
            if -shot.radius <= shot.position.x <= SCREEN_WIDTH + shot.radius and -shot.radius <= shot.position.y <= SCREEN_HEIGHT + shot.radius:
                live.append(shot)
        self.projectiles = live
        return hit

    def remove_ball(self, ball):
        self.remove_quantum_ball(ball)
        if ball.body.space is self.space:
            self.space.remove(ball.shape, ball.body)
        self.by_body.pop(ball.body, None)
        self.wall_impacts.discard(ball)
        self.paddle_impacts.discard(ball)
        self.wave_contacts.pop(ball, None)
        self.remove_ghost_for(ball)
        self.balls.remove(ball)

    def fit_to_solids(self, position, radius):
        """Separacion local al crear/fusionar: no busca una zona aleatoria."""
        pos = V(*position)
        for _ in range(4):
            pos = V(clamp(pos.x, LEFT + radius + 8.6, RIGHT - radius - 8.6),
                    clamp(pos.y, TOP + radius + 8.6, BOTTOM - radius - 8.6))
            query = self.paddle_shape.point_query(pos)
            if query.distance >= radius + .6:
                break
            pos += query.gradient * (radius + .6 - query.distance)
        return pos

    def split_ball(self, parent):
        if self.active != 'fission' or self.fusion_progress is not None:
            return
        if parent not in self.balls or self.sim_time < parent.split_ready_at:
            return
        group = parent.fission_group
        if group is None:
            group = id(parent)
            self.fission_originals[group] = parent
        center, velocity = parent.body.position, parent.body.velocity
        tangent = V(math.cos(self.paddle.angle), math.sin(self.paddle.angle))
        normal = V(tangent.y, -tangent.x)
        radius = max(FISSION_MIN_RADIUS, parent.radius / math.sqrt(2))
        mass = max(1e-6, parent.body.mass / 2)
        mirror = normal * (2 * velocity.dot(normal)) - velocity
        self.remove_ball(parent)
        for sign, outgoing in ((-1, velocity), (1, mirror)):
            pos = self.fit_to_solids(center + tangent * (sign * (radius + .7)), radius)
            child = Ball(self.space, pos, outgoing, radius)
            child.body.mass = mass
            child.body.moment = pymunk.moment_for_circle(mass, 0, radius)
            child.fission_group = group
            # Evita que el contacto de nacimiento cuente como un segundo golpe.
            child.split_ready_at = self.sim_time + .10
            self.balls.append(child)
            self.by_body[child.body] = child
        self.burst(center, POWERUPS['fission'][2], 14)

    def begin_fusion(self):
        self.fusion_progress = 0.0
        self.fusion_starts = {}
        for group in self.fission_originals:
            family = [b for b in self.balls if b.fission_group == group]
            self.fusion_centers[group] = sum((b.body.position for b in family), V(0, 0)) / len(family)
            self.fusion_velocities[group] = sum((b.body.velocity for b in family), V(0, 0)) / len(family)
            for ball in family:
                self.fusion_starts[ball] = V(*ball.body.position)
                self.space.remove(ball.shape, ball.body)
                self.by_body.pop(ball.body, None)
        self.message, self.message_left = 'NUCLEAR FUSION', 1.3

    def step_fusion(self, dt):
        if self.fusion_progress is None:
            return False
        self.fusion_progress = min(1.0, self.fusion_progress + dt / FUSION_DURATION)
        progress = self.fusion_progress
        ease = progress * progress * (3 - 2 * progress)
        hit = False
        for ball, origin in self.fusion_starts.items():
            start = ball.body.position
            ball.previous = start
            end = origin.interpolate_to(self.fusion_centers[ball.fission_group], ease)
            ball.body.position = end
            if self.target_lock <= 0 and swept_circle(start, end, self.target, ball.radius + TARGET_RADIUS):
                hit = True
        if progress >= 1 - 1e-9:
            for ball in tuple(self.fusion_starts):
                self.remove_ball(ball)
            for group, original in self.fission_originals.items():
                pos = self.fit_to_solids(self.fusion_centers[group], original.radius)
                original.body.position = pos
                original.body.velocity = self.fusion_velocities[group]
                original.previous = pos
                original.trail.clear()
                self.space.add(original.body, original.shape)
                self.balls.append(original)
                self.by_body[original.body] = original
                self.burst(pos, POWERUPS['fission'][2], 20)
            self.fission_originals.clear()
            self.fusion_starts.clear()
            self.fusion_centers.clear()
            self.fusion_velocities.clear()
            self.fusion_progress = None
            self.finish_powerup()
        return hit

    def start_wave(self, ball):
        ball.wave_active = True
        ball.trail = deque(maxlen=1440)
        ball.wave_trail_clock = 0.0
        self.reset_wave(ball, ball.body.velocity)

    def reset_wave(self, ball, velocity):
        velocity = V(*velocity)
        speed = velocity.length
        if speed > MAX_BALL_SPEED:
            velocity *= MAX_BALL_SPEED / speed
        ball.wave_center = V(*ball.body.position)
        ball.wave_velocity = velocity
        ball.wave_incoming_base = velocity
        ball.wave_phase = 0.0
        ball.wave_axis = V(-velocity.y, velocity.x).normalized() if speed > 20 else V(1, 0)
        ball.body.velocity = velocity

    def prepare_wave(self, ball, dt):
        # El centro lleva la velocidad ordinaria; solo la particula tiene forma
        # de colision. La frecuencia depende de la rapidez, la amplitud no.
        speed = ball.wave_velocity.length
        frequency = self.wave_frequency(speed)
        phase = (ball.wave_phase + math.tau * frequency * dt) % math.tau
        old_offset = ball.wave_axis * (WAVE_AMPLITUDE * math.sin(ball.wave_phase))
        next_velocity = ball.wave_velocity + self.space.gravity * dt
        # Pymunk aplica gravedad durante este subpaso. Guardar el centro
        # entrante permite resolver colisiones independientemente de la fase.
        ball.wave_incoming_base = next_velocity
        desired = V(-next_velocity.y, next_velocity.x).normalized() if next_velocity.length > 1 else ball.wave_axis
        # Normal local de Frenet, con orientacion continua. Cerca de velocidad
        # cero el diedro es singular: transportar el marco evita un salto de 180°.
        if desired.dot(ball.wave_axis) < 0:
            desired = -desired
        angle = math.atan2(ball.wave_axis.cross(desired), ball.wave_axis.dot(desired))
        next_axis = ball.wave_axis.rotated(clamp(angle, -WAVE_FRAME_MAX_TURN * dt, WAVE_FRAME_MAX_TURN * dt))
        new_offset = next_axis * (WAVE_AMPLITUDE * math.sin(phase))
        ball.wave_step_velocity = (new_offset - old_offset) / dt
        ball.wave_next_phase, ball.wave_next_offset, ball.wave_next_axis = phase, new_offset, next_axis
        ball.body.velocity = ball.wave_velocity + ball.wave_step_velocity

    @staticmethod
    def wave_frequency(speed):
        blend = clamp((speed - 400) / (MAX_BALL_SPEED - 400), 0.0, 1.0)
        blend = blend * blend * (3 - 2 * blend)
        return max(WAVE_REST_FREQUENCY, speed / WAVE_WAVELENGTH * (1 + blend))

    def resolve_wave(self, ball):
        contacts = self.wave_contacts.pop(ball, None)
        if contacts:
            outgoing = ball.wave_incoming_base
            for normal, surface, elasticity, share in contacts:
                # La pelota visible determina DONDE se toca la superficie;
                # el centro balistico determina la direccion y energia del bote.
                # Una oscilacion que roza una pared al alejarse no invierte otra
                # vez el centro, evitando botes de ida y vuelta y adherencias.
                relative = outgoing - surface
                outgoing -= normal * ((1 + elasticity) * min(0, relative.dot(normal)) * share)
            self.reset_wave(ball, outgoing)
            # La primera semionda tras el choque se abre hacia dentro del campo.
            inward = sum((contact[0] for contact in contacts), V(0, 0))
            if ball.wave_axis.dot(inward) < 0:
                ball.wave_axis = -ball.wave_axis
        else:
            ball.wave_phase = ball.wave_next_phase
            ball.wave_axis = ball.wave_next_axis
            ball.wave_center = ball.body.position - ball.wave_next_offset
            velocity = ball.body.velocity - ball.wave_step_velocity
            if velocity.length > MAX_BALL_SPEED:
                velocity *= MAX_BALL_SPEED / velocity.length
            ball.wave_velocity = velocity

    def grow_giant(self, ball, increase=True):
        if self.active != 'giant' or ball not in self.balls:
            return
        if increase:
            ball.giant_goal_radius *= 1.20
        radius = ball.giant_goal_radius
        if radius <= ball.radius + 1e-6:
            return
        ball.resize(self.space, radius)
        if ball.shape.sensor:
            self.contain_ball(ball)
            pos = ball.body.position
        else:
            pos = self.fit_to_solids(ball.body.position, radius)
            if not self.safe_position(pos, radius, ignore=ball):
                pos = self.free_position(radius, ignore=ball) or pos
        self.teleport(ball, pos)
        self.burst(pos, POWERUPS['giant'][2], 9)

    def award_target(self, collector=None, target_index=0):
        if self.active == 'analytical' and target_index > 0:
            if self.award_analytical_target(target_index):
                self.hits += 1
            return
        self.score += self.score_multiplier if self.active == 'double' else 1
        self.hits += 1
        target = self.snell_targets[target_index] if self.active == 'snell' else self.target
        self.burst(target, TargetRendererMixin.TARGET_COLORS[self.target_style], 20)
        if self.active == 'snell':
            self.replace_snell_target(target_index)
            self.snell_target_locks[target_index] = .08
            self.target = self.snell_targets[0]
            return
        if self.active == 'giant' and collector is not None:
            self.grow_giant(collector)
        self.target = self.free_position(TARGET_RADIUS + 12) or self.target
        self.target_lock = .08
        if self.active == 'wormhole':
            self.on_target_changed_wormhole()

    def burst(self, pos, color, count):
        if not self.effects:
            return
        self.rings.append([pos.x, pos.y, 0.0, color])
        self.rings = self.rings[-12:]
        for _ in range(min(count, max(0, 240 - len(self.particles)))):
            angle, speed = self.fx_rng.uniform(0, math.tau), self.fx_rng.uniform(60, 240)
            life = self.fx_rng.uniform(0.3, 0.65)
            self.particles.append([pos.x, pos.y, math.cos(angle) * speed, math.sin(angle) * speed, life, life, color])

    def tick_effects(self, dt):
        self.message_left = max(0.0, self.message_left - dt)
        self.fortune_reveal_left = max(0.0, self.fortune_reveal_left - dt)
        alive = []
        for p in self.particles:
            p[4] -= dt
            if p[4] > 0:
                p[0] += p[2] * dt
                p[1] += p[3] * dt
                p[3] += 100 * dt
                alive.append(p)
        self.particles = alive
        for ring in self.rings:
            ring[2] += dt
        self.rings = [r for r in self.rings if r[2] < 0.5]

    def set_paddle_velocity(self, controls, subdt):
        if self.active == 'drone':
            self.paddle.velocity = (0, 0)
            self.paddle.angular_velocity = 0.0
            return
        angle = clamp(self.paddle.angle + controls.turn * self.aspeed * subdt, -MAX_ANGLE, MAX_ANGLE)
        # La punta alcanza la cara interior de la pared a maxima inclinacion.
        # El limite no cambia al girar: evita desplazar la pala lateralmente de
        # golpe y permite que el extremo horizontal quede oculto tras la pared.
        inset = PADDLE_HALF * math.cos(MAX_ANGLE) + 8.0 + self.paddle_shape.radius
        x = clamp(self.paddle.position.x + controls.move * self.hspeed * 100 * subdt, LEFT + inset, RIGHT - inset)
        self.paddle.velocity = ((x - self.paddle.position.x) / subdt, 0)
        self.paddle.angular_velocity = (angle - self.paddle.angle) / subdt

    def contain_ball(self, ball):
        """Correccion local de penetracion. Nunca relanza ni cambia de zona."""
        p, v, r = ball.body.position, ball.body.velocity, ball.radius
        if ball.shape.sensor:
            coordinates, velocities = [], []
            for coordinate, velocity, lo, hi in ((p.x, v.x, LEFT + 8, RIGHT - 8),
                                                 (p.y, v.y, TOP + 8, BOTTOM - 8)):
                if 2 * r >= hi - lo:
                    coordinates.append((lo + hi) * .5)
                    velocities.append(0.0)
                else:
                    clamped = clamp(coordinate, lo + r, hi - r)
                    coordinates.append(clamped)
                    velocities.append(-velocity * BALL_ELASTICITY * WALL_ELASTICITY
                                      if (clamped - coordinate) * velocity < 0 else velocity)
            ball.body.position, ball.body.velocity = coordinates, velocities
            self.space.reindex_shapes_for_body(ball.body)
            return False
        x = clamp(p.x, LEFT + 8 + r, RIGHT - 8 - r)
        y = clamp(p.y, TOP + 8 + r, BOTTOM - 8 - r)
        if abs(x - p.x) > 0.5 or abs(y - p.y) > 0.5:
            self.safety_corrections += 1
            bounce_x = (p.x < x and v.x < -1) or (p.x > x and v.x > 1)
            bounce_y = (p.y < y and v.y < -1) or (p.y > y and v.y > 1)
            bounce = 1.0 if self.active == 'overdrive' else BALL_ELASTICITY * WALL_ELASTICITY
            vx = -v.x * bounce if bounce_x else v.x
            vy = -v.y * bounce if bounce_y else v.y
            ball.body.position = (x, y)
            ball.body.velocity = (vx, vy)
            if self.active == 'overdrive' and ((bounce_x and abs(v.x) >= TURBO_MIN_IMPACT)
                                               or (bounce_y and abs(v.y) >= TURBO_MIN_IMPACT)):
                self.wall_impacts.add(ball)
            query = self.paddle_shape.point_query(ball.body.position)
            if query.distance < r - .5 and y > BOTTOM - r - 14:
                # Entre pala y suelo: proyectar sobre la cara superior local,
                # manteniendo la coordenada horizontal y evitando un salto aleatorio.
                vertices = [self.paddle.local_to_world(vtx) for vtx in PADDLE_VERTICES[:4]]
                for a, b in zip(vertices, vertices[1:]):
                    if min(a.x, b.x) <= x <= max(a.x, b.x) and abs(b.x - a.x) > 1e-6:
                        surface_y = a.y + (b.y - a.y) * (x - a.x) / (b.x - a.x)
                        slope = (b.y - a.y) / (b.x - a.x)
                        ball.body.position = (x, surface_y - (r + .6) * math.sqrt(1 + slope * slope))
                        ball.body.velocity = (vx, min(vy, 0))
                        break
            self.space.reindex_shapes_for_body(ball.body)
            return False
        return False

    def step(self, controls=None):
        controls = controls or Controls()
        self.sim_time += FIXED_DT
        self.update_powerup(FIXED_DT)
        self.tick_quantum(FIXED_DT)
        self.tick_drone_effects(FIXED_DT)
        if self.drone_collector is not None:
            self.drone_previous_angle = self.drone_collector.body.angle
        self.target_lock = max(0.0, self.target_lock - FIXED_DT)
        if self.active == 'snell':
            self.snell_target_locks = [max(0.0, timer - FIXED_DT) for timer in self.snell_target_locks]
        self.tick_effects(FIXED_DT)
        self.step_snell(FIXED_DT)
        self.previous_paddle, self.previous_angle = self.paddle.position, self.paddle.angle
        for ball in self.balls:
            ball.previous = ball.body.position
            if not ball.wave_active:
                ball.limit_speed(self.speed_limit)
        # Presupuesto conservador incluso DESPUES de un rebote en este tick.
        # Viaje relativo <= 40% del radio minimo: evita saltar la barra/pared.
        radius = min((ball.radius for ball in self.balls), default=BALL_RADIUS)
        if self.active == 'fission':
            radius = min(radius, FISSION_MIN_RADIUS)
        tip_speed = abs(controls.move) * self.hspeed * 100 + abs(controls.turn) * self.aspeed * PADDLE_HALF
        relative_speed = max(2 * self.speed_limit, self.speed_limit + tip_speed)
        substeps = max(1, math.ceil(relative_speed * FIXED_DT / (0.4 * radius)))
        subdt = FIXED_DT / substeps
        hit_targets = {}
        target_positions = self.active_targets()
        collected = None
        collector = None
        for _ in range(substeps):
            drone_start = V(*self.drone_collector.body.position) if self.drone_collector is not None else None
            self.set_paddle_velocity(controls, subdt)
            self.prepare_drone(controls, subdt)
            self.prepare_gaussian(controls, subdt)
            physical = [ball for ball in self.balls if ball.body.space is self.space]
            starts = [ball.body.position for ball in physical]
            braking = (self.explosion_carrier if self.active == 'explosion'
                       and not self.exploded and self.active_left <= .65 else None)
            for ball in physical:
                if self.active == 'satellite':
                    ball.body.velocity += self.satellite_acceleration(ball.body.position) * subdt
                    ball.limit_speed(self.speed_limit)
                elif ball.wave_active:
                    self.prepare_wave(ball, subdt)
                elif ball is braking:
                    ball.body.velocity *= math.exp(-10 * subdt)
                    if self.active_left <= .04:
                        ball.body.velocity = (0, 0)
                ball.portal_incoming_velocity = V(*ball.body.velocity)
            self.space.step(subdt)
            crashed = self.resolve_drone_crash()
            self.apply_quantum_impulses(hit_targets)
            for ball, start in zip(physical, starts):
                if ball is braking:
                    ball.body.velocity -= self.space.gravity * subdt
                transported = self.handle_portal(ball, start) if self.active == 'mobius' else False
                snell_segments = self.handle_snell(ball, start, subdt) if self.active == 'snell' else None
                self.contain_ball(ball)
                if ball in self.wall_impacts:
                    self.boost_ball(ball)
                    self.wall_impacts.discard(ball)
                if ball.wave_active:
                    self.resolve_wave(ball)
                    ball.wave_trail_clock += subdt
                    if ball.wave_trail_clock >= 1 / 960:
                        ball.wave_trail_clock %= 1 / 960
                        ball.trail.append(ball.body.position)
                else:
                    ball.limit_speed(DRONE_MAX_SPEED if ball is self.drone_collector else self.speed_limit)
                end = ball.body.position
                sensor_end = ball.portal_entry_position if transported else end
                if crashed is not None and ball is crashed[0]:
                    sensor_end = crashed[1]
                segments = snell_segments or [(start, sensor_end)]
                if transported:
                    segments.append((end, end))
                for index, target in target_positions:
                    if (index not in hit_targets and self.target_ready(index)
                            and any(swept_circle(a, b, target, ball.radius + TARGET_RADIUS) for a, b in segments)):
                        hit_targets[index] = ball
                if self.pickup and collected is None and swept_star(start, sensor_end, self.pickup.position, ball.radius):
                    collected = self.pickup.kind
                    collector = ball
                if self.active == 'wormhole':
                    self.capture_wormhole(ball, start, end)
            self.step_drone_ordnance(subdt, hit_targets, drone_start)
            self.resolve_quantum_observations()
            for ball in tuple(self.balls):
                if ball in self.paddle_impacts:
                    if self.active == 'fission':
                        self.split_ball(ball)
                    elif self.active == 'timewarp':
                        self.refresh_ghost(ball)
            self.paddle_impacts.clear()
        if self.step_ghosts(FIXED_DT) | self.step_fusion(FIXED_DT):
            hit_targets.setdefault(0, None)
        self.step_projectiles(FIXED_DT, hit_targets)
        self.step_analytical(FIXED_DT, hit_targets)
        for index, target_collector in hit_targets.items():
            self.award_target(target_collector, target_index=index)
        if self.active == 'analytical' and self.analytical_phase == 'release':
            self.finish_powerup()
        if collected:
            self.activate_powerup(collected, collector)
        elif self.active == 'voronoi':
            self.step_voronoi(FIXED_DT)
        self.step_wormhole(FIXED_DT)
        self._trail_clock += FIXED_DT
        trail_tick = self._trail_clock >= 1 / 120
        if trail_tick:
            self._trail_clock -= 1 / 120
            if self.pending_balls and self.sim_time % .25 < FIXED_DT * 2:
                self.pending_balls -= 1
                self.add_ball()
            if self.active == 'giant' and self.sim_time % .1 < FIXED_DT * 2:
                for ball in self.balls:
                    self.grow_giant(ball, increase=False)
        for ball in self.balls:
            if trail_tick and self.trail_style != 4 and not ball.wave_active:
                ball.trail.append(ball.body.position)
        if trail_tick:
            for shot in self.projectiles:
                shot.trail.append(shot.position)
        self.step_gaussian(controls, FIXED_DT)


class SimulationClock:
    """Acumulador comun a la aplicacion y a las pruebas 30/60/120/360 FPS."""
    def __init__(self):
        self.accumulator = 0.0

    def advance(self, world, elapsed, controls):
        self.accumulator += clamp(elapsed, 0.0, MAX_FRAME_DT)
        steps = 0
        while self.accumulator + 1e-12 >= FIXED_DT:
            world.step(controls)
            self.accumulator = max(0.0, self.accumulator - FIXED_DT)
            steps += 1
        return steps

    @property
    def alpha(self):
        return self.accumulator / FIXED_DT


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    action: str


TARGET_STYLES = ('CLASSIC', 'MAGIC ORB', 'BULLSEYE', 'ELECTRIC', 'BLACK HOLE',
                 'ATOM', 'SPACETIME', 'PRISM', 'GOLD')


class TargetRendererMixin:
    """Animated cosmetic targets. Every solid core keeps the real hit radius."""

    TARGET_COLORS = ((60, 225, 235), (191, 139, 255), (255, 104, 129),
                     (103, 224, 255), (255, 172, 91), (104, 241, 199),
                     (117, 157, 255), (193, 221, 255), (255, 208, 90))

    @lru_cache(maxsize=24)
    def _target_sphere(self, color, radius):
        """Reusable enamel/metal shading; no per-frame surface allocations."""
        radius = max(1, int(radius))
        image = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        center = V(radius + 2, radius + 2)
        for ring in range(radius, 0, -1):
            depth = 1 - ring / radius
            brightness = .25 + .66 * math.sin(depth * math.pi * .70)
            tone = tuple(round(channel * brightness) for channel in color)
            offset = V(-.24, -.30) * radius * depth
            pygame.draw.circle(image, tone, center + offset, ring)
        for ring in range(max(1, radius // 3), 0, -1):
            strength = (1 - ring / max(1, radius / 3)) ** .7
            tone = tuple(round(channel + (255 - channel) * strength * .75) for channel in color)
            pygame.draw.circle(image, (*tone, 190), center + V(-.31, -.39) * radius, ring)
        return image

    def draw_target(self, world, target, target_index=0):
        style = int(getattr(world, 'target_style', 0)) % len(TARGET_STYLES)
        ready = world.target_ready(target_index) if hasattr(world, 'target_ready') else True
        self._draw_target_art(style, self.project(target), TARGET_RADIUS * DRAW_SCALE,
                              world.sim_time + target_index * .47, ready)

    def _draw_target_art(self, style, center, radius, phase, ready=True):
        s, c = self.canvas, V(*center)
        r = max(1.0, radius)
        base = self.TARGET_COLORS[style]
        fade = 1.0 if ready else .38
        tint = lambda color, strength=1.0: self.shade(color, strength * fade)
        polar = lambda angle, length=1.0: c + V(math.cos(angle), math.sin(angle)) * r * length

        def ring(color, scale=1.0, width=1):
            pygame.draw.circle(s, tint(color), c, max(1, round(r * scale)), width)

        def curve(points, color, strength=1.0, width=1, closed=False):
            if width > 1:
                pygame.draw.lines(s, tint(color, strength), closed, points, width)
            pygame.draw.aalines(s, tint(color, strength), closed, points)

        def spark(point, size, color, strength=1.0):
            length = max(1, size)
            tone = tint(color, strength)
            pygame.draw.aaline(s, tone, point - V(length, 0), point + V(length, 0))
            pygame.draw.aaline(s, tone, point - V(0, length), point + V(0, length))
            pygame.draw.circle(s, tint((248, 252, 255), strength), point, 1)

        self.halo(c, tint(base, .75), round(r * (2.1 if style in (1, 3, 8) else 1.8)))
        if style == 0:
            pulse = math.sin(phase * 4)
            pygame.draw.circle(s, tint(base, .16), c, round(r + 7 + pulse * 2))
            ring(base, 1, 2)
            pygame.draw.circle(s, tint(base), c, max(2, round(r * .25)))
            return

        if style == 1:
            # An opalescent, breathing orb inside a broken rune circle.
            image = self._target_sphere((148, 113, 235), round(r))
            if ready:
                s.blit(image, image.get_rect(center=c))
            else:
                pygame.draw.circle(s, tint(base, .3), c, round(r))
            for layer in range(3):
                offset = phase * (.75 if layer % 2 else -.56) + layer * math.tau / 3
                cloud = [c + V(math.cos(a) * .83, math.sin(a) * .29).rotated(offset) * r
                         for a in (i * math.tau / 36 for i in range(37))]
                curve(cloud, ((126, 240, 247), (244, 160, 244), (205, 181, 255))[layer], .6)
            ring((225, 196, 255), 1.0)
            for index in range(7):
                angle = phase * .28 + index * math.tau / 7
                arc = [polar(angle + j * .047, 1.31) for j in range(9)]
                curve(arc, base, .63)
                if index % 2 == 0:
                    spark(polar(angle + .14, 1.5), 2 + math.sin(phase * 3 + index),
                          (222, 203, 255), .68)
            spark(c + V(-.31, -.43) * r, r * .20, (250, 233, 255))

        elif style == 2:
            # A real bullseye, with precise enamel rings and revolving sights.
            for scale, color in ((1, (252, 230, 220)), (.79, base), (.56, (250, 231, 222)),
                                 (.34, base), (.14, (255, 232, 140))):
                pygame.draw.circle(s, tint(color), c, max(1, round(r * scale)))
            ring((255, 249, 244), 1.0)
            for index in range(4):
                angle = phase * .45 + index * math.pi / 2
                curve([polar(angle + offset, 1.20) for offset in (-.15, 0, .15)], base, .78)
                pygame.draw.aaline(s, tint((255, 237, 201), .75), polar(angle, 1.18), polar(angle, 1.43))
            curve([c + V(-.62, -.4) * r, c + V(-.39, -.62) * r], (255, 255, 255), .7, 2)

        elif style == 3:
            # Independent continuous corona leaders; no gameplay random calls.
            pygame.draw.circle(s, tint(base, .09), c, round(r))
            ring(base, 1)
            tick = phase * 18
            for branch in range(6):
                angle = phase * .32 + branch * math.tau / 6
                normal = V(-math.sin(angle), math.cos(angle))
                direction = V(math.cos(angle), math.sin(angle))
                points = []
                for index in range(7):
                    reach = .18 + index * .16
                    noise = math.sin(index * 7.21 + branch * 4.17 + tick) * math.sin(index * 3.43 - tick * .71)
                    points.append(c + direction * (r * reach) + normal * (noise * r * .18))
                curve(points, base, .22, 4)
                curve(points, (198, 248, 255), .9)
                if branch % 2 == 0:
                    fork = [points[3], points[3] + normal * r * .26 + direction * r * .16,
                            points[3] + normal * r * .40 + direction * r * .40]
                    curve(fork, (143, 151, 255), .73)
            self.halo(c, (127, 226, 255), round(r * .65))
            pygame.draw.circle(s, tint((168, 242, 255)), c, max(2, round(r * .27)))
            pygame.draw.circle(s, tint((242, 253, 255)), c, max(1, round(r * .13)))

        elif style == 4:
            # The luminous accretion disc passes behind and in front of a dark
            # spherical horizon. The thin inner rim marks the physical target.
            for back in (True, False):
                start = math.pi if back else 0
                for band in range(4):
                    scale = 1.14 + band * .13
                    points = [c + V(math.cos(a) * scale, math.sin(a) * scale * .33).rotated(-.33) * r
                              for a in (start + i * math.pi / 36 for i in range(37))]
                    curve(points, ((255, 234, 168), (255, 163, 80), (203, 112, 147), (125, 112, 211))[band],
                          (.43 if back else .93) - band * .12)
                if back:
                    pygame.draw.circle(s, (3, 5, 12), c, round(r))
                    ring((235, 157, 90), 1)
                    ring((99, 80, 115), .88)
            for index in range(6):
                angle = phase * (1.1 + (index % 2) * .35) + index * math.tau / 6
                point = c + V(math.cos(angle) * 1.50, math.sin(angle) * .50).rotated(-.33) * r
                pygame.draw.circle(s, tint((255, 218, 159), .65), point, 1)

        elif style == 5:
            # Three tilted orbital planes, with front/back depth on electrons.
            pygame.draw.circle(s, tint(base, .045), c, round(r))
            ring(base, 1, 1)
            palette = ((117, 244, 204), (144, 183, 255), (255, 169, 225))
            for index, color in enumerate(palette):
                rotation = index * math.pi / 3 + .12 * math.sin(phase * .45)
                orbit = [c + V(math.cos(a) * 1.32, math.sin(a) * .46).rotated(rotation) * r
                         for a in (i * math.tau / 48 for i in range(49))]
                curve(orbit[:25], color, .31)
                curve(orbit[24:], color, .77)
                angle = phase * (2.1 + index * .21) + index * 2.1
                electron = c + V(math.cos(angle) * 1.32, math.sin(angle) * .46).rotated(rotation) * r
                self.halo(electron, color, max(3, round(r * .34)))
                pygame.draw.circle(s, tint(color), electron, max(2, round(r * .12)))
                pygame.draw.circle(s, tint((247, 253, 255)), electron, 1)
            for offset, color in ((V(-.13, .07), (255, 183, 198)), (V(.12, .08), (157, 228, 255)),
                                  (V(0, -.13), (213, 245, 194))):
                pygame.draw.circle(s, tint(color), c + offset * r, max(2, round(r * .21)))

        elif style == 6:
            # A toroidal spacetime lattice: meridians twist through its centre,
            # while travelling highlights make the mesh flow around the ring.
            pygame.draw.circle(s, tint(base, .075), c, round(r))
            ring((170, 201, 255), 1)
            for latitude in range(5):
                theta = latitude * math.pi / 4
                rx = .69 + .29 * math.cos(theta)
                ry = .70 + .29 * math.sin(theta + math.pi / 2)
                points = [c + V(math.cos(a) * rx, math.sin(a) * ry).rotated(-.28) * r
                          for a in (i * math.tau / 48 for i in range(49))]
                curve(points, (110, 165, 255), .28 + .08 * latitude)
            for index in range(12):
                angle = phase * .43 + index * math.tau / 12
                outer = polar(angle, .98)
                inner = polar(angle + .37, .34)
                control = polar(angle + .12, .77)
                points = [(1 - t) ** 2 * outer + 2 * (1 - t) * t * control + t * t * inner
                          for t in (j / 8 for j in range(9))]
                curve(points, (122, 232, 245) if index % 3 == 0 else base, .64)
            pygame.draw.circle(s, (5, 10, 25), c, max(1, round(r * .32)))
            ring((193, 163, 255), .34)
            for index in range(3):
                spark(polar(phase * .9 + index * math.tau / 3, .73), 2, (209, 240, 255), .73)

        elif style == 7:
            # A transparent-looking faceted crystal with drifting dispersion.
            palette = ((255, 132, 184), (255, 209, 131), (157, 245, 186),
                       (123, 225, 255), (155, 157, 255), (226, 155, 255))
            vertices = [polar(-math.pi / 2 + index * math.tau / 8, 1) for index in range(8)]
            core = c + V(-.16, -.10) * r
            for index, (a, b) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
                light = .23 + .13 * (1 + math.sin(phase * 1.6 + index))
                pygame.draw.polygon(s, tint(palette[index % 6], light), (core, a, b))
                pygame.draw.aaline(s, tint(palette[index % 6], .62), core, a)
            curve(vertices, (221, 238, 255), .91, closed=True)
            for index in range(6):
                start = c + V(.31, -.13 + index * .07) * r
                end = c + V(1.32, -.63 + index * .19) * r
                pygame.draw.aaline(s, tint(palette[index], .35 + .13 * math.sin(phase * 2 + index)), start, end)
            curve([c + V(-1.24, -.40) * r, core], (227, 247, 255), .70)
            spark(c + V(-.34, -.47) * r, r * .25, (252, 250, 255))
            ring((204, 221, 255), .98)

        elif style == 8:
            # A polished gold sphere, animated with an orbiting star glint.
            image = self._target_sphere((255, 195, 55), round(r))
            if ready:
                s.blit(image, image.get_rect(center=c))
            else:
                pygame.draw.circle(s, tint(base, .3), c, round(r))
            ring((255, 225, 129), 1)
            curve([polar(a, .82) for a in (1.1 + i * .034 for i in range(37))], (255, 183, 40), .75, 2)
            curve([polar(a, .86) for a in (3.52 + i * .030 for i in range(27))], (255, 246, 208), .88, 2)
            glint = c + V(math.cos(phase * .66) * .51, math.sin(phase * .66) * .46) * r
            spark(glint, r * (.15 + .10 * max(0, math.sin(phase * 2.2))), (255, 251, 218))
            for index in range(4):
                angle = index * math.pi / 2 + phase * .20
                shine = max(0, math.sin(phase * 2.0 + index * 2.9))
                if shine > .2:
                    spark(polar(angle, 1.34), 1 + shine * 2.6, (255, 221, 122), shine * .75)


class Renderer(AnalyticalRendererMixin, TargetRendererMixin, GaussianRendererMixin, DroneRendererMixin, QuantumRendererMixin):
    def __init__(self):
        self.canvas = pygame.Surface((WIDTH, HEIGHT))
        self.background = pygame.Surface((WIDTH, HEIGHT))
        self.fonts = {size: pygame.font.SysFont("consolas", size, bold=(size >= 24))
                      for size in (14, 16, 18, 20, 24, 30, 34, 48)}
        self.pause_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.pause_overlay.fill((3, 8, 18, 195))
        self.status_overlay = pygame.Surface((540, 64), pygame.SRCALPHA)
        pygame.draw.rect(self.status_overlay, (*BG, 218), (0, 0, 540, 64), border_radius=10)
        self._voronoi_world = None
        self._voronoi_geometry = None
        self._voronoi_cells = []
        self._voronoi_edges = []
        self._wormhole_geometry = {}
        self.snell_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        field_left, field_top = round(LEFT * DRAW_SCALE), round(TOP * DRAW_SCALE)
        field_right, glass_y = round(RIGHT * DRAW_SCALE), round((TOP + BOTTOM) * .5 * DRAW_SCALE)
        pygame.draw.rect(self.snell_overlay, (111, 133, 255, 10),
                         (field_left, field_top, field_right - field_left, glass_y - field_top))
        for offset in range(-200, field_right - field_left, 168):
            points = ((field_left + offset, field_top), (field_left + offset + 48, field_top),
                      (field_left + offset + 236, glass_y), (field_left + offset + 208, glass_y))
            pygame.draw.polygon(self.snell_overlay, (143, 181, 255, 4), points)
        self.make_background()

    @lru_cache(maxsize=256)
    def text(self, value, size=18, color=INK):
        if size not in self.fonts:
            self.fonts[size] = pygame.font.SysFont("consolas", size, bold=(size >= 24))
        return self.fonts[size].render(value, True, color)

    def fitted_label(self, value, center, width, size=18, color=INK):
        image = self.text(value, size, color)
        if image.get_width() > width:
            scale = width / image.get_width()
            image = pygame.transform.smoothscale(image, (round(width), max(1, round(image.get_height() * scale))))
        self.canvas.blit(image, image.get_rect(center=center))

    def draw_fortune(self, world):
        if world.active != 'double':
            return
        exponent = world.score_multiplier.bit_length() - 1
        reveal = min(1.0, world.fortune_reveal_left / 1.4)
        size = min(280, 86 + 12 * exponent)
        tint = self.shade(GOLD, .10 + .11 * reveal)
        self.fitted_label(multiplier_text(world.score_multiplier), (WIDTH // 2, 375), 900, size, tint)
        self.label("FORTUNE FAVOURS THE BOLD", (WIDTH // 2, 270), 16,
                   self.shade(GOLD, .20 + .22 * reveal), True)
        for index in range(7):
            angle = index * math.tau / 7 + world.sim_time * .16
            point = V(WIDTH / 2, 370) + V(math.cos(angle) * 280, math.sin(angle) * 115)
            self.star(point, 4 + index % 3, self.shade(GOLD, .2 + .2 * reveal), angle)

    def draw_power_symbol(self, kind, center, color, radius=30):
        """Faceted collectible with a pictogram (or Analytical Path's f(x))."""
        c = V(*center)
        phase = getattr(self, '_visual_time', 0.0)
        s = self.canvas
        self.halo(c, color, round(radius * 1.9))
        vertices = star_vertices(c, radius)
        for index, (a, b) in enumerate(zip(vertices, vertices[1:] + vertices[:1])):
            shine = .5 + .5 * math.sin(index * .8 - phase * 1.7)
            if kind == 'double':
                tint = (round(202 + 53 * shine), round(122 + 105 * shine), round(27 + 94 * shine))
            else:
                tint = self.shade(color, .33 + .36 * shine)
            pygame.draw.polygon(s, tint, (c, a, b))
        pygame.draw.aalines(s, color, True, vertices)
        # A dark enamel centre keeps tiny pictograms legible at pickup size.
        pygame.draw.circle(s, self.shade(color, .09), c, max(2, round(radius * .52)))
        pygame.draw.circle(s, self.shade(color, .47), c, max(2, round(radius * .51)), 1)
        unit = radius * .40
        bright = tuple(round(channel * .20 + 255 * .80) for channel in color)
        weight = 2 if radius >= 32 else 1

        def point(x, y):
            return c + V(x, y) * unit

        def line(points, tint=bright, width=weight, closed=False):
            mapped = [point(x, y) for x, y in points]
            if width > 1:
                pygame.draw.lines(s, tint, closed, mapped, width)
            pygame.draw.aalines(s, tint, closed, mapped)

        def dot(x, y, size, tint=bright, hollow=False):
            pygame.draw.circle(s, tint, point(x, y), max(1, round(size * unit)), 1 if hollow else 0)

        if kind == 'giant':
            dot(0, .13, .43, bright, True)
            for angle in (-math.pi / 2, math.pi / 6, math.pi * 5 / 6):
                direction = V(math.cos(angle), math.sin(angle))
                normal = V(-direction.y, direction.x)
                end = direction * 1.02
                line((direction * .61, end))
                line((end - direction * .29 + normal * .20, end,
                      end - direction * .29 - normal * .20))
        elif kind == 'multiball':
            for x, y, r in ((0, -.60, .29), (-.58, .34, .30), (.58, .34, .30), (0, .15, .15)):
                dot(x, y, r, bright, r > .2)
        elif kind == 'overdrive':
            line(((-.95, -.60), (-.39, 0), (-.95, .60)), self.shade(color, .7))
            line(((-.38, -.70), (.27, 0), (-.38, .70)))
            line(((.28, -.55), (.84, 0), (.28, .55)))
        elif kind == 'double':
            # Cut gemstone on a gold medal: fortune without typographic symbols.
            line(((-.79, -.28), (-.39, -.73), (.39, -.73), (.79, -.28), (0, .82)), GOLD, closed=True)
            line(((-.79, -.28), (.79, -.28)), bright)
            line(((-.39, -.73), (-.28, -.28), (0, .82), (.28, -.28), (.39, -.73)), bright)
        elif kind == 'satellite':
            orbit = [(math.cos(i * math.tau / 32), .43 * math.sin(i * math.tau / 32)) for i in range(33)]
            line([V(*p).rotated(-.45) for p in orbit], color)
            dot(0, 0, .33)
            dot(.74, -.54, .20, bright)
        elif kind == 'explosion':
            for index in range(10):
                direction = V(math.cos(index * math.tau / 10), math.sin(index * math.tau / 10))
                line((direction * .50, direction * (1.01 if index % 2 else .85)), color)
            dot(0, 0, .27)
            dot(0, 0, .46, bright, True)
        elif kind == 'mobius':
            loop = [(.99 * math.cos(i * math.tau / 44), .51 * math.sin(i * math.tau / 22))
                    for i in range(45)]
            line(loop[:23], (113, 190, 255))
            line(loop[22:], (255, 183, 109))
        elif kind == 'fission':
            for angle in (-math.pi / 2, math.pi / 6, math.pi * 5 / 6):
                end = V(math.cos(angle), math.sin(angle)) * .78
                line(((0, 0), end), color)
                dot(end.x, end.y, .23, bright, True)
            dot(0, 0, .22)
        elif kind == 'duality':
            line(((-1.04, 0), (1.04, 0)), self.shade(color, .40))
            line([(-1.02 + index * 2.04 / 30, -.58 * math.sin(index * math.tau / 20))
                  for index in range(31)])
            dot(.34, .5, .19, color)
        elif kind == 'timewarp':
            arc = [(.84 * math.cos(-2.0 + index * 5.25 / 30),
                    .84 * math.sin(-2.0 + index * 5.25 / 30)) for index in range(31)]
            line(arc, color)
            line(((-1.02, -.33), (-.84, -.10), (-.59, -.29)))
            line(((0, -.54), (0, 0), (.42, .28)))
            dot(0, 0, .11)
        elif kind == 'voronoi':
            hexagon = [(math.cos(i * math.tau / 6), math.sin(i * math.tau / 6)) for i in range(6)]
            line(hexagon, color, closed=True)
            line(((-1, 0), (-.20, -.25), (.30, .24), (1, 0)), bright)
            line(((-.20, -.25), (0, -.86)), (255, 162, 220))
            line(((.30, .24), (.14, .86)), (156, 194, 255))
            for x, y in ((-.49, .35), (.48, -.35), (-.39, -.55)):
                dot(x, y, .09, GOLD)
        elif kind == 'wormhole':
            for index in range(4):
                scale = .90 - index * .18
                dx = -.18 + index * .14
                ring = [(dx + .62 * scale * math.cos(i * math.tau / 24),
                         scale * math.sin(i * math.tau / 24)) for i in range(25)]
                line(ring, bright if index == 0 else self.shade(color, 1 - index * .16))
            line(((-.18, -.90), (.50, -.23)), color)
            line(((-.18, .90), (.50, .23)), color)
        elif kind == 'snell':
            line(((-.57, .66), (0, -.76), (.61, .66)), bright, closed=True)
            line(((-1.08, -.26), (-.26, -.10)), bright)
            for y, tint in ((-.49, (255, 143, 179)), (-.09, (138, 241, 219)), (.33, (137, 176, 255))):
                line(((.23, -.09), (1.05, y)), tint)
        elif kind == 'quantum':
            line(((-.63, -.48), (-.21, -.13), (-.40, .05), (.16, .18), (.63, .48)), bright)
            dot(-.65, -.49, .29, (255, 112, 146), True)
            dot(.65, .49, .29, (115, 190, 255), True)
            dot(-.65, -.49, .12, (255, 153, 175))
            dot(.65, .49, .12, (160, 215, 255))
        elif kind == 'gaussian':
            line([(-1.06 + i * 2.12 / 32, .62 - 1.40 * math.exp(-((-1.06 + i * 2.12 / 32) / .53) ** 2))
                  for i in range(33)])
            line(((-1.07, .68), (1.07, .68)), color)
            for x, y in ((0, .01), (-.22, .28), (.22, .28), (-.44, .51), (0, .51), (.44, .51)):
                dot(x, y, .06, color)
        elif kind == 'drone':
            line(((-.70, -.15), (-.31, .16), (.31, .16), (.70, -.15)), color)
            line(((-.31, .16), (-.19, .44), (.19, .44), (.31, .16)), bright)
            for x in (-.73, .73):
                line(((x, -.38), (x, .09)))
                line(((x - .35, -.39), (x + .35, -.39)))
                line(((x - .21, -.58), (x + .21, -.58)), color)
            dot(0, .23, .13, bright)
        elif kind == 'analytical':
            # Explicit mathematical emblem requested for this powerup.
            self.label('f(x)', c, max(8, round(radius * .46)), bright, True)

    def draw_modal(self, app, mouse):
        self.canvas.blit(self.pause_overlay, (0, 0))
        s = self.canvas
        if app.modal == 'powerups':
            panel = pygame.Rect(155, 125, 1290, 670)
            pygame.draw.rect(s, PANEL, panel, border_radius=20)
            pygame.draw.rect(s, (64, 88, 119), panel, 2, border_radius=20)
            self.star((195, 172), 20, GOLD)
            self.label('THE POWERUP ARCHIVE', (235, 150), 30, INK)
            self.label(f'{len(app.world.discovered):02d} / {len(POWERUPS):02d} DISCOVERED', (236, 190), 16, CYAN)
            hovered = None
            columns = 4
            rows = max(1, math.ceil(len(POWERUPS) / columns))
            pitch_y = min(149, 476 // rows)
            card_height = pitch_y - 10
            for index, (kind, (title, description, color)) in enumerate(POWERUPS.items()):
                rect = pygame.Rect(185 + (index % columns) * 309,
                                   234 + (index // columns) * pitch_y, 296, card_height)
                known = kind in app.world.discovered
                over = mouse is not None and rect.collidepoint(mouse)
                pygame.draw.rect(s, (24, 37, 58) if known else (12, 21, 35), rect, border_radius=12)
                pygame.draw.rect(s, color if known and over else (51, 71, 94) if known else (28, 42, 60),
                                 rect, 2 if known and over else 1, border_radius=12)
                self.label(f'{index + 1:02d}', (rect.x + 12, rect.y + 10), 14, MUTED)
                center = (rect.centerx, rect.y + card_height * .38)
                if known:
                    self.draw_power_symbol(kind, center, color, min(30, card_height * .28))
                    self.fitted_label(title, (rect.centerx, rect.bottom - 19), rect.width - 22, 16, color)
                else:
                    self.star(center, min(30, card_height * .28), (35, 46, 64))
                    self.label('?', center, 24, (88, 108, 133), True)
                    self.label('UNDISCOVERED', (rect.centerx, rect.bottom - 19), 14, (85, 102, 126), True)
                if over:
                    hovered = description if known else 'Catch this star during a run to reveal its place in the archive.'
            self.fitted_label(hovered or 'Every discovery stays with you. Catch a star to unlock its entry.',
                              (WIDTH // 2, 748), 1170, 18, MUTED)
        else:
            panel = pygame.Rect(490, 304, 620, 292)
            pygame.draw.rect(s, PANEL, panel, border_radius=20)
            pygame.draw.rect(s, (65, 94, 127), panel, 2, border_radius=20)
            exiting = app.modal == 'quit'
            if app.modal == 'setting' and app.pending_setting is not None:
                field, value = app.pending_setting
                name = 'MOVEMENT' if field == 'hspeed' else 'ROTATION'
                self.label('RESET SCORE?', (800, 363), 30, INK, True)
                self.label(f'{name}: {getattr(app.world, field)}  >  {value}', (800, 412), 22, CYAN, True)
                self.label('Applying this change will reset your score to 0.', (800, 451), 16, MUTED, True)
            else:
                self.label('LEAVE THE ARENA?' if exiting else 'START A NEW RUN?', (800, 363), 30, INK, True)
                self.label('Your discoveries will be kept.', (800, 417), 18, MUTED, True)
                self.label('This run will end.' if exiting else 'Your score and active powerup will reset.',
                           (800, 451), 16, MUTED, True)
        for button in app.modal_buttons():
            over = mouse is not None and button.rect.collidepoint(mouse)
            pygame.draw.rect(s, (40, 77, 88) if over else (26, 44, 65), button.rect, border_radius=9)
            pygame.draw.rect(s, CYAN if over else (65, 100, 127), button.rect, 1, border_radius=9)
            self.label(button.label, button.rect.center, 18, INK, True)

    def label(self, value, xy, size=18, color=INK, center=False):
        image = self.text(value, size, color)
        self.canvas.blit(image, image.get_rect(center=xy) if center else xy)

    @staticmethod
    def project(position):
        return V(position[0] * DRAW_SCALE, position[1] * DRAW_SCALE)

    @staticmethod
    def shade(color, strength):
        return tuple(int(BG[i] + (color[i] - BG[i]) * strength) for i in range(3))

    @lru_cache(maxsize=64)
    def glow(self, color, radius):
        """Halos pequenos reutilizados: ninguna superficie por bola/fotograma."""
        radius = max(1, int(radius))
        glow = pygame.Surface((radius * 2 + 2, radius * 2 + 2), pygame.SRCALPHA)
        center = (radius + 1, radius + 1)
        for step in range(10, 0, -1):
            r = max(1, round(radius * step / 10))
            pygame.draw.circle(glow, (*color, int(3 + 32 * (1 - step / 10) ** 2)), center, r)
        return glow

    def halo(self, position, color, radius):
        glow = self.glow(color, int(radius))
        self.canvas.blit(glow, glow.get_rect(center=position))

    def make_background(self):
        s = self.background
        s.fill(BG)
        pygame.draw.rect(s, PANEL, (36, 20, 1528, 94), border_radius=18)
        left, right = round(LEFT * DRAW_SCALE), round(RIGHT * DRAW_SCALE)
        top, bottom = round(TOP * DRAW_SCALE), round(BOTTOM * DRAW_SCALE)
        field = pygame.Rect(left, top, right - left, bottom - top)
        pygame.draw.rect(s, (11, 19, 33), field, border_radius=8)
        for x in range(left + 24, right - 8, 32):
            for y in range(top + 24, bottom - 8, 32):
                pygame.draw.circle(s, (21, 34, 49), (x, y), 1)
        for width, color in ((13, (18, 61, 77)), (4, (57, 123, 146)), (1, (124, 208, 214))):
            pygame.draw.rect(s, color, field.inflate(width, width), width, border_radius=9)
        for x in range(left + 24, right - 8, 16):
            pygame.draw.line(s, (28, 56, 67), (x, bottom + 10), (x + 5, bottom + 5), 1)
        pygame.draw.rect(s, PANEL, (36, 816, 1528, 66), border_radius=16)

    def star(self, center, radius, color, rotation=0.0):
        center = V(*center)
        points = star_vertices(center, radius)
        if rotation:
            points = [center + (point - center).rotated(rotation) for point in points]
        pygame.draw.polygon(self.canvas, color, points)

    def draw_trail(self, trail, position, radius, color, style, sparse=False):
        if style == 4 or len(trail) < 2:
            return
        points = [self.project(p) for p in trail]
        if sparse:
            points = points[::3]
        if (points[-1] - position).length_squared > 0.05:
            points.append(position)
        if len(points) < 2:
            return
        if style == 0:
            points = points[-9:]
            count = len(points)
            for index, point in enumerate(points[:-1]):
                strength = (index + 1) / count
                pygame.draw.circle(self.canvas, self.shade(color, strength * 0.32), point,
                                   max(1, round(radius * strength * 0.65)))
        elif style == 1:
            # Un trazo fino continuo deja ver toda la trayectoria reciente.
            pygame.draw.lines(self.canvas, self.shade(color, 0.17), False, points, 3)
            pygame.draw.aalines(self.canvas, self.shade(color, 0.48), False, points)
            pygame.draw.aalines(self.canvas, self.shade(color, 0.78), False,
                               points[max(0, len(points) - 6):])
        elif style == 2:
            # Cometa: doce tramos cortos que se afinan y apagan hacia la cola.
            points = points[-13:]
            count = len(points) - 1
            for index in range(count):
                strength = (index + 1) / count
                width = max(1, round(radius * strength * 1.2))
                tone = self.shade(color, 0.12 + 0.48 * strength)
                pygame.draw.line(self.canvas, tone, points[index], points[index + 1], width)
                if width > 2:
                    pygame.draw.circle(self.canvas, tone, points[index + 1], width // 2)
        elif style == 3:
            for index in range(0, len(points) - 1, 3):
                strength = (index + 1) / len(points)
                end = points[min(index + 1, len(points) - 1)]
                pygame.draw.line(self.canvas, self.shade(color, 0.15 + strength * 0.5),
                                 points[index], end, max(1, round(radius * 0.25)))
        elif style == 8:
            # A short fairy-dust wake. Bounded distance sampling keeps dense
            # multi-ball scenes cheap; animated twinkles never touch game RNG.
            phase = getattr(self, '_visual_time', 0.0)
            extent, spacing = 195.0, 12.0 if sparse else 5.5
            sampled, distances = [points[-1]], [0.0]
            last, traveled, next_sample = points[-1], 0.0, spacing
            for point in reversed(points[:-1]):
                delta = point - last
                length = delta.length
                if length < 1e-8:
                    last = point
                    continue
                take = min(length, extent - traveled)
                while next_sample <= traveled + take + 1e-8:
                    sampled.append(last + delta * ((next_sample - traveled) / length))
                    distances.append(next_sample)
                    next_sample += spacing
                endpoint = last + delta * (take / length)
                traveled += take
                last = point
                if traveled >= extent - .001:
                    break
            if traveled > distances[-1] + .25:
                sampled.append(endpoint)
                distances.append(traveled)
            if len(sampled) < 2:
                return
            palette = (color, (255, 217, 133), (219, 165, 255), (166, 239, 255))
            spread = clamp(radius * .85, 5, 15)
            for index, (point, distance) in enumerate(zip(sampled[1:], distances[1:]), 1):
                fade = (1 - distance / max(1, distances[-1])) ** .70
                if fade <= 0:
                    continue
                delta = sampled[min(index + 1, len(sampled) - 1)] - sampled[index - 1]
                tangent = delta.normalized() if delta.length_squared > 1e-8 else V(1, 0)
                normal = V(-tangent.y, tangent.x)
                dust_phase = index * 2.39996
                drift = math.sin(dust_phase + phase * .8) * spread * (.5 + .8 * (1 - fade))
                speck = point + normal * drift + V(0, -4 * (1 - fade) * math.sin(phase + index))
                twinkle = .48 + .52 * math.sin(phase * (3.8 + index % 3) + dust_phase) ** 6
                tint = palette[index % 4]
                strength = fade * twinkle
                if index % 3 == 0 and not sparse:
                    self.halo(speck, tint, 5)
                pygame.draw.circle(self.canvas, self.shade(tint, .83 * strength), speck,
                                   2 if index % 4 == 0 and strength > .35 else 1)
                if index % 5 == 0 and strength > .22:
                    size = 1.2 + strength * 3
                    bright = self.shade((255, 245, 219), strength)
                    pygame.draw.aaline(self.canvas, bright, speck - V(size, 0), speck + V(size, 0))
                    pygame.draw.aaline(self.canvas, bright, speck - V(0, size * 1.35), speck + V(0, size * 1.35))
                if index < 8:
                    pygame.draw.aaline(self.canvas, self.shade(color, .13 * fade),
                                       sampled[index - 1], point)
        elif style in (5, 6, 7):
            # Arc-length sampling keeps the helix/grid legible at any ball speed.
            # Work is bounded by visual length, including for giant balls.
            extent = 205.0 if style == 5 else 172.0 if style == 6 else 188.0
            spacing = 10.0 if sparse else (4.0 if style in (5, 7) else 6.0)
            sampled, distances = [points[-1]], [0.0]
            for point in reversed(points[:-1]):
                start = sampled[-1]
                delta = point - start
                length = delta.length
                if length < .25:
                    continue
                take = min(length, extent - distances[-1])
                count = max(1, math.ceil(take / spacing))
                origin = distances[-1]
                for step in range(1, count + 1):
                    travel = take * step / count
                    sampled.append(start + delta * (travel / length))
                    distances.append(origin + travel)
                if distances[-1] >= extent - .001:
                    break
            if len(sampled) < 3 or distances[-1] < 2:
                return
            if style == 7:
                # Irregular electric leaders need long, readable facets rather
                # than a comb of tiny zigzags on densely sampled slow trails.
                stride = 15.0 if sparse else 7.0
                total = distances[-1]
                even_points, even_distances = [sampled[0]], [0.0]
                cursor, index = stride, 1
                while cursor < total:
                    while index < len(distances) - 1 and distances[index] < cursor:
                        index += 1
                    fraction = (cursor - distances[index - 1]) / max(.001, distances[index] - distances[index - 1])
                    even_points.append(sampled[index - 1] + (sampled[index] - sampled[index - 1]) * fraction)
                    even_distances.append(cursor)
                    cursor += stride
                even_points.append(sampled[-1])
                even_distances.append(total)
                sampled, distances = even_points, even_distances
            tangents, normals = [], []
            for index, point in enumerate(sampled):
                delta = sampled[min(index + 1, len(sampled) - 1)] - sampled[max(0, index - 1)]
                tangent = delta.normalized() if delta.length_squared > 1e-8 else V(1, 0)
                tangents.append(tangent)
                normals.append(V(-tangent.y, tangent.x))
            phase = getattr(self, '_visual_time', 0.0)
            fades = [(1 - distance / max(1.0, distances[-1])) ** .65 for distance in distances]
            if style == 5:
                # Complementary strands rotate in opposite depth planes; rungs
                # and illuminated bases make the double helix recognisable.
                cyan, rose = (93, 235, 255), (255, 127, 190)
                amplitude = clamp(radius * .95, 6, 13)
                turns = [distance * math.tau / 54 - phase * 3.2 for distance in distances]
                offsets = [math.sin(turn) * amplitude * (.4 + .6 * fade)
                           for turn, fade in zip(turns, fades)]
                strands = [[point + normal * offset * sign
                            for point, normal, offset in zip(sampled, normals, offsets)]
                           for sign in (-1, 1)]
                next_rung = 4.0
                for index, distance in enumerate(distances):
                    if distance < next_rung:
                        continue
                    next_rung += 10.0
                    a, b = strands[0][index], strands[1][index]
                    middle, fade = (a + b) * .5, fades[index]
                    pygame.draw.aaline(self.canvas, self.shade(cyan, .43 * fade), a, middle)
                    pygame.draw.aaline(self.canvas, self.shade(rose, .43 * fade), middle, b)
                    if not sparse:
                        for endpoint, tint in ((a, cyan), (b, rose)):
                            pygame.draw.circle(self.canvas, self.shade(tint, .85 * fade), endpoint, 2)
                for strand_index, (strand, tint) in enumerate(zip(strands, (cyan, rose))):
                    stride = 5 if sparse else 3
                    for index in range(0, len(strand) - 1, stride):
                        depth = .65 + .35 * math.cos(turns[index] + strand_index * math.pi)
                        strength = fades[index] * (.43 + .5 * depth)
                        section = strand[index:index + stride + 1]
                        if not sparse:
                            pygame.draw.lines(self.canvas, self.shade(tint, strength * .18), False, section, 4)
                        pygame.draw.aalines(self.canvas, self.shade(tint, strength), False, section)
            elif style == 6:
                # A short wireframe throat, with elliptical ribs moving towards
                # the ball and five longitudinal rails following its real path.
                blue, cyan = (130, 144, 255), (88, 231, 232)
                widths = [clamp(radius * .98, 1, 23) * (.10 + .90 * fade ** .8) for fade in fades]
                left = [point - normal * width for point, normal, width in zip(sampled, normals, widths)]
                right = [point + normal * width for point, normal, width in zip(sampled, normals, widths)]
                pygame.draw.polygon(self.canvas, self.shade(blue, .045), left + right[::-1])
                for fraction in (-1, -.5, 0, .5, 1):
                    rail = [point + normal * width * fraction
                            for point, normal, width in zip(sampled, normals, widths)]
                    tint = cyan if fraction > 0 else blue
                    stride = max(3, len(rail) // (6 if sparse else 10))
                    for index in range(0, len(rail) - 1, stride):
                        strength = fades[index] * (.58 if abs(fraction) == 1 else .25)
                        pygame.draw.aalines(self.canvas, self.shade(tint, strength), False,
                                           rail[index:index + stride + 1])
                next_ring = (phase * 28) % 17
                for index, distance in enumerate(distances):
                    if distance < next_ring:
                        continue
                    next_ring += 17
                    point, normal, tangent, width = sampled[index], normals[index], tangents[index], widths[index]
                    ring = [point + normal * (math.cos(i * math.tau / 18) * width)
                            + tangent * (math.sin(i * math.tau / 18) * (2 + width * .2))
                            for i in range(19)]
                    pygame.draw.aalines(self.canvas, self.shade(blue, .38 * fades[index]), False, ring)
                    pygame.draw.aalines(self.canvas, self.shade(cyan, .78 * fades[index]), False, ring[9:])
            else:
                # Short, live corona: a white-hot leader, coloured counter-arc
                # and a handful of forks. Deterministic noise never consumes
                # gameplay RNG, and dense multiball uses the same bounded path.
                ice, violet = (158, 242, 255), (157, 138, 255)
                amplitude = clamp(radius * .90, 5, 15)
                tick = math.floor(phase * 32)
                blend = phase * 32 - tick
                blend = blend * blend * (3 - 2 * blend)
                arcs = []
                for branch in range(1 if sparse else 2):
                    arc = []
                    for index, (point, normal, distance, fade) in enumerate(zip(sampled, normals, distances, fades)):
                        hash_a = math.sin(index * 127.1 + tick * 311.7 + branch * 83.19) * 43758.5453
                        hash_b = math.sin(index * 127.1 + (tick + 1) * 311.7 + branch * 83.19) * 43758.5453
                        a = (hash_a - math.floor(hash_a)) * 2 - 1
                        b = (hash_b - math.floor(hash_b)) * 2 - 1
                        noise = a + (b - a) * blend
                        envelope = fade ** .55 * min(1, distance / 14)
                        offset = noise * amplitude * envelope * (1 if branch == 0 else .75)
                        arc.append(point + normal * offset)
                    arcs.append(arc)
                for branch, arc in reversed(list(enumerate(arcs))):
                    tint = ice if branch == 0 else violet
                    stride = 5 if sparse else 3
                    for index in range(0, len(arc) - 1, stride):
                        strength = fades[index] * (1 if branch == 0 else .67)
                        section = arc[index:index + stride + 1]
                        if not sparse:
                            pygame.draw.lines(self.canvas, self.shade(tint, strength * .10), False, section, 7)
                            pygame.draw.lines(self.canvas, self.shade(tint, strength * .34), False, section, 3)
                        pygame.draw.aalines(self.canvas, self.shade(tint, strength), False, section)
                        if branch == 0 and strength > .35:
                            pygame.draw.aalines(self.canvas, self.shade((230, 253, 255), strength * .88),
                                               False, section[:2])
                leader = arcs[0]
                for fork in range(1 if sparse else 4):
                    index = min(len(leader) - 2, max(1, (fork + 1) * len(leader) // 6))
                    start = leader[index]
                    normal, tangent, fade = normals[index], tangents[index], fades[index]
                    side = 1 if (fork + tick // 3) % 2 else -1
                    length = (8 + 6 * math.sin(tick * .37 + fork) ** 2) * fade
                    bend = start + normal * side * length * .55 + tangent * 4
                    end = start + normal * side * length + tangent * 11
                    fork_points = (start, bend, bend - normal * side * 3 + tangent * 4, end)
                    pygame.draw.aalines(self.canvas, self.shade(color, fade * .74), False, fork_points)
                    if not sparse and fork % 2 == 0:
                        pygame.draw.aaline(self.canvas, self.shade(ice, fade * .55), end - normal * 2, end + normal * 2)

    def draw_satellite(self, world):
        center = self.project(world.target)
        color = POWERUPS["satellite"][2]
        self.halo(center, color, 160)
        for radius in (65, 112, 166, 224):
            pygame.draw.circle(self.canvas, self.shade(color, 0.17 - radius / 2400), center, radius, 1)
            phase = world.sim_time * (0.5 + 80 / radius) + radius
            dot = center + V(math.cos(phase), math.sin(phase)) * radius
            pygame.draw.circle(self.canvas, self.shade(color, 0.5), dot, 2)

    def wormhole_geometry(self, route):
        """La rejilla proyectada se conserva hasta que cambia su destino."""
        key = id(route)
        cached = self._wormhole_geometry.get(key)
        if cached is not None and cached[0] is route:
            return cached[1:]
        if len(self._wormhole_geometry) >= 24:
            self._wormhole_geometry.clear()
        points = [self.project(point) for point in route.points]
        normals = []
        for index, point in enumerate(points):
            delta = points[min(index + 1, len(points) - 1)] - points[max(0, index - 1)]
            tangent = delta.normalized() if delta.length_squared > 1e-8 else V(0, -1)
            normals.append(V(-tangent.y, tangent.x))
        distances = [distance * DRAW_SCALE for distance in route.cumulative]
        self._wormhole_geometry[key] = (route, points, normals, distances)
        return points, normals, distances

    def draw_wormhole_route(self, route, progress, opacity, sim_time, branch=False):
        points, normals, distances = self.wormhole_geometry(route)
        if len(points) < 2 or opacity <= 0:
            return
        total = max(1.0, route.length * DRAW_SCALE)
        visible_length = total * clamp(progress, 0, 1)
        end_index = 1
        while end_index < len(points) and distances[end_index] < visible_length:
            end_index += 1
        end_index = min(end_index, len(points) - 1)
        points = points[:end_index + 1]
        normals = normals[:end_index + 1]
        distances = distances[:end_index + 1]
        if progress < 1 and len(points) > 1:
            start_distance = distances[-2]
            fraction = clamp((visible_length - start_distance) / max(.001, distances[-1] - start_distance), 0, 1)
            points[-1] = points[-2] + (points[-1] - points[-2]) * fraction
            distances[-1] = visible_length
        widths = [(30 * (1 - distance / total) ** 1.65 + 10) * (0.65 if branch else 1)
                  for distance in distances]
        color, secondary = (112, 160, 255), (91, 244, 229)
        left = [point - normal * width for point, normal, width in zip(points, normals, widths)]
        right = [point + normal * width for point, normal, width in zip(points, normals, widths)]
        # El fondo oscuro, las costillas y los meridianos dan volumen sin tapar el juego.
        if not branch:
            pygame.draw.polygon(self.canvas, self.shade(color, .035 * opacity), left + right[::-1])
        for rail, tint in ((left, color), (right, secondary)):
            pygame.draw.lines(self.canvas, self.shade(tint, .10 * opacity), False, rail, 8)
            pygame.draw.lines(self.canvas, self.shade(tint, .23 * opacity), False, rail, 3)
            pygame.draw.aalines(self.canvas, self.shade(tint, .63 * opacity), False, rail)
        for fraction in (-.48, 0, .48):
            meridian = [point + normal * width * fraction
                        for point, normal, width in zip(points, normals, widths)]
            pygame.draw.aalines(self.canvas, self.shade(color, (.16 if fraction else .08) * opacity),
                               False, meridian)
        # Las elipses avanzan en longitud de arco: la animacion no acelera en las curvas.
        spacing = 42.0
        cursor = (sim_time * 48) % spacing
        while cursor < visible_length:
            center, tangent = route.point_at(cursor / DRAW_SCALE)
            center = self.project(center)
            normal = V(-tangent.y, tangent.x)
            width = (30 * (1 - cursor / total) ** 1.65 + 10) * (0.65 if branch else 1)
            ring = [center + normal * (math.cos(i * math.tau / 20) * width)
                    + tangent * (math.sin(i * math.tau / 20) * (3.5 + width * .12))
                    for i in range(21)]
            pygame.draw.aalines(self.canvas, self.shade(color, .28 * opacity), False, ring)
            highlight = ring[10:]
            pygame.draw.aalines(self.canvas, self.shade(secondary, .38 * opacity), False, highlight)
            cursor += spacing
        if 0 < progress < 1:
            tip = points[-1]
            self.halo(tip, secondary, 35)
            pygame.draw.line(self.canvas, self.shade(secondary, opacity),
                             tip - normals[-1] * widths[-1], tip + normals[-1] * widths[-1], 2)

    def draw_wormhole(self, world):
        entry = getattr(world, "wormhole_entry", None)
        route = getattr(world, "wormhole_route", None)
        if entry is None or route is None:
            return
        closing = getattr(world, "wormhole_close_left", 0.0)
        opacity = clamp(closing / .35, 0, 1) if closing > 0 else 1.0
        build = getattr(world, "wormhole_build", 1.0)
        self.draw_wormhole_route(route, build, opacity, world.sim_time)
        branches = set()
        for transit in getattr(world, "wormhole_transits", {}).values():
            if (transit.route is route or id(transit.route) in branches
                    or transit.route.points[-2:] == route.points[-2:]):
                continue
            branches.add(id(transit.route))
            if len(branches) > 8:
                break
            self.draw_wormhole_route(transit.route, 1, opacity * .32, world.sim_time, True)
        center = self.project(entry)
        opening = clamp(build / .22, 0, 1)
        radius = 44 * DRAW_SCALE * (.35 + .65 * opening) * (.35 + .65 * opacity)
        cyan, violet = (112, 235, 255), (156, 131, 255)
        self.halo(center, cyan, 66)
        pygame.draw.circle(self.canvas, (6, 12, 26), center, max(1, round(radius - 1)))
        for index in range(4):
            r = radius * (.35 + .17 * index)
            tone = self.shade(violet, opacity * (.10 + .055 * index))
            pygame.draw.circle(self.canvas, tone, center, max(1, round(r)), 1)
        for width, strength in ((9, .11), (5, .25), (2, .88)):
            pygame.draw.circle(self.canvas, self.shade(cyan, opacity * strength), center,
                               max(1, round(radius)), width)
        for index in range(3):
            phase = world.sim_time * .8 + index * math.tau / 3
            start, end = phase, phase + .9
            arc = [center + V(math.cos(start + (end - start) * i / 12),
                             math.sin(start + (end - start) * i / 12)) * (radius + 5)
                   for i in range(13)]
            pygame.draw.lines(self.canvas, self.shade(violet, .8 * opacity), False, arc, 2)
        for index in range(7):
            progress = (world.sim_time * .45 + index / 7) % 1
            phase = index * 2.4 + progress * 1.8
            point = center + V(math.cos(phase), math.sin(phase)) * (radius * (1 - progress))
            pygame.draw.circle(self.canvas, self.shade(cyan, .85 * opacity * (1 - progress)), point, 1)
        if opening > .9:
            self.label("ENTRANCE", (center.x, center.y + radius + 18), 14,
                       self.shade(cyan, .65 * opacity), True)

    def draw_snell(self, world):
        if world.active != "snell":
            return
        self.canvas.blit(self.snell_overlay, (0, 0))
        y = round(getattr(world, "snell_line_y", (TOP + BOTTOM) / 2) * DRAW_SCALE)
        left, right = round(LEFT * DRAW_SCALE), round(RIGHT * DRAW_SCALE)
        palette = ((161, 126, 255), (100, 158, 255), (103, 240, 244),
                   (149, 245, 183), (247, 230, 136), (255, 156, 176))
        for width, strength in ((17, .045), (9, .10), (4, .19)):
            pygame.draw.line(self.canvas, self.shade((127, 209, 255), strength), (left, y), (right, y), width)
        pygame.draw.aaline(self.canvas, self.shade(INK, .73), (left, y), (right, y))
        for index, x in enumerate(range(left, right, 42)):
            color = palette[index % len(palette)]
            strength = .35 + .16 * math.sin(world.sim_time * 1.4 - index * .7)
            end = min(right, x + 42)
            pygame.draw.line(self.canvas, self.shade(color, strength), (x, y - 2), (end, y - 2))
            pygame.draw.line(self.canvas, self.shade(palette[(index + 2) % len(palette)], strength * .7),
                             (x, y + 2), (end, y + 2))
            facet = (V(x + 3, y), V(x + 17, y - 7), V(x + 31, y))
            pygame.draw.aalines(self.canvas, self.shade(color, .18), False, facet)
        for flash in getattr(world, "snell_flashes", ()):
            age = flash.age
            strength = clamp(1 - age / .65, 0, 1)
            center = self.project(flash.position)
            self.halo(center, (192, 228, 255), 46)
            extent = 8 + age * 105
            for index, color in enumerate(palette):
                angle = index * math.pi / 3 + math.pi / 6
                direction = V(math.cos(angle), math.sin(angle))
                start = center + direction * (extent * .24)
                end = center + direction * extent
                pygame.draw.line(self.canvas, self.shade(color, strength * .25), start, end, 5)
                pygame.draw.aaline(self.canvas, self.shade(color, strength * .85), start, end)
            pygame.draw.circle(self.canvas, self.shade(INK, strength), center, max(1, round(4 * strength)))

    def draw_rainbow_projectile(self, projectile, pos, trail_style):
        palette = ((167, 121, 255), (99, 146, 255), (92, 225, 252),
                   (124, 247, 175), (249, 234, 121), (255, 171, 119), (255, 136, 184))
        points = [self.project(point) for point in projectile.trail]
        if points and (points[-1] - pos).length_squared > .05:
            points.append(pos)
        if len(points) > 1 and trail_style != 4:
            count = len(points) - 1
            for index, color in enumerate(palette):
                start = round(index * count / len(palette))
                end = round((index + 1) * count / len(palette))
                if end <= start:
                    continue
                section = points[start:end + 1]
                brightness = .34 + .60 * (index + 1) / len(palette)
                pygame.draw.lines(self.canvas, self.shade(color, brightness * .18), False, section, 7)
                pygame.draw.lines(self.canvas, self.shade(color, brightness * .4), False, section, 3)
                pygame.draw.aalines(self.canvas, self.shade(color, brightness), False, section)
        self.halo(pos, (206, 194, 255), 18)
        pygame.draw.circle(self.canvas, (173, 218, 255), pos, max(2, round(projectile.radius * DRAW_SCALE)))
        pygame.draw.circle(self.canvas, INK, pos, 2)

    def draw_wave_trail(self, trail, position, color, sparse=False):
        """Dos segundos de onda, con brillo concentrado en el frente."""
        if len(trail) < 2:
            return
        points = [self.project(point) for point in trail]
        # Retain the physics samples: dropping every other point aliases the
        # doubled high-speed frequency, especially close to a reflected crest.
        if (points[-1] - position).length_squared > 0.05:
            points.append(position)
        count = len(points) - 1
        stride = max(1, count // 24)
        for index in range(0, count, stride):
            chunk = points[index:min(index + stride + 1, len(points))]
            age = (index + stride) / max(1, count)
            tone = tuple(round(color[i] * (1 - age * 0.45) + CYAN[i] * age * 0.45) for i in range(3))
            if not sparse:
                pygame.draw.lines(self.canvas, self.shade(tone, 0.09 + age * 0.14), False, chunk, 4)
            pygame.draw.aalines(self.canvas, self.shade(tone, 0.08 + age ** 1.4 * 0.78), False, chunk)

    def draw_portals(self, world):
        # Lineas planas sobre el muro: el interior luminoso marca el paso.
        for portal in world.portals:
            center = self.project(portal.position)
            tangent, normal = portal.tangent, portal.normal
            age = max(0.0, world.sim_time - portal.created_at)
            opening = min(1.0, age / 0.16)
            extent = portal.half_length * DRAW_SCALE * (0.25 + 0.75 * opening)
            start, end = center - tangent * extent, center + tangent * extent
            pulse = 0.8 + 0.2 * math.sin(world.sim_time * 5 + center.x * 0.02 + center.y * 0.03)
            for width, strength in ((17, 0.12), (11, 0.25), (6, 0.55), (2, pulse)):
                pygame.draw.line(self.canvas, self.shade(portal.color, strength), start, end, width)
            pygame.draw.aaline(self.canvas, INK, start + normal * 2, end + normal * 2)
            for tip in (start, end):
                pygame.draw.circle(self.canvas, portal.color, tip, 3)
            for index in range(4):
                phase = (world.sim_time * 0.7 + index / 4) % 1
                pos = center + tangent * ((phase * 2 - 1) * extent)
                offset = 3 + 7 * math.sin(phase * math.pi)
                pygame.draw.circle(self.canvas, self.shade(portal.color, (1 - phase) * 0.7),
                                   pos + normal * offset, 1)

    def draw_ghosts(self, world, alpha):
        color = POWERUPS["timewarp"][2]
        sparse = len(world.ghosts) > 60
        for ghost in world.ghosts.values():
            # El futuro es fino y discontinuo; el rastro recorrido tiene mas brillo.
            forecast = [self.project(point) for point in getattr(ghost, "forecast_points", ())]
            if len(forecast) > 1:
                pygame.draw.aalines(self.canvas, self.shade(color, 0.13), False, forecast)
                stride = max(2, len(forecast) // (36 if sparse else 90))
                for index in range(0, len(forecast) - 1, stride * 2):
                    section = forecast[index:min(index + stride + 1, len(forecast))]
                    strength = 0.23 - 0.10 * index / len(forecast)
                    pygame.draw.aalines(self.canvas, self.shade(color, strength), False, section)
                for index, impact in enumerate(getattr(ghost, "forecast_impacts", ())):
                    point = self.project(impact)
                    tone = self.shade(color, 0.36 - 0.018 * index)
                    pygame.draw.circle(self.canvas, tone, point, 3, 1)
            hit = getattr(ghost, "forecast_hit_pos", None)
            if hit is not None:
                point = self.project(hit)
                hit_color = (158, 255, 200)
                pulse = 0.7 + 0.3 * math.sin(world.sim_time * 5)
                self.halo(point, hit_color, 18)
                diamond = (point + V(0, -6), point + V(6, 0),
                           point + V(0, 6), point + V(-6, 0))
                pygame.draw.aalines(self.canvas, self.shade(hit_color, pulse), True, diamond)
                target = self.project(world.target)
                radius = TARGET_RADIUS * DRAW_SCALE + 12
                for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                    start = target + V(math.cos(angle), math.sin(angle)) * radius
                    end = target + V(math.cos(angle), math.sin(angle)) * (radius + 5)
                    pygame.draw.line(self.canvas, self.shade(hit_color, pulse * 0.7), start, end, 2)
            pos = self.project(ghost.previous * (1 - alpha) + ghost.position * alpha)
            radius = max(2, round(ghost.radius * DRAW_SCALE))
            trail = [self.project(point) for point in ghost.trail]
            if sparse:
                trail = trail[::3]
            if world.trail_style != 4 and len(trail) > 1:
                trail.append(pos)
                middle = max(1, len(trail) // 2)
                pygame.draw.aalines(self.canvas, self.shade(color, 0.13), False, trail)
                pygame.draw.lines(self.canvas, self.shade(color, 0.19), False, trail[middle:], 3)
                pygame.draw.aalines(self.canvas, self.shade(color, 0.5), False, trail[-8:])
            self.halo(pos, color, 25)
            pygame.draw.circle(self.canvas, self.shade(color, 0.12), pos, radius)
            pygame.draw.circle(self.canvas, color, pos, radius, 1)
            pygame.draw.circle(self.canvas, self.shade(INK, 0.7), pos, max(2, radius // 3))
            orbit = V(math.cos(ghost.phase), math.sin(ghost.phase)) * (radius + 4)
            pygame.draw.circle(self.canvas, self.shade(color, 0.65), pos + orbit, 1)
            pygame.draw.circle(self.canvas, self.shade(color, 0.4), pos - orbit, 1)

    def prepare_voronoi(self, world):
        """Cache de geometria proyectada: se prepara una sola vez por diagrama."""
        geometry = world.voronoi_cells
        if self._voronoi_world is world and self._voronoi_geometry is geometry:
            return
        self._voronoi_world, self._voronoi_geometry = world, geometry
        self._voronoi_cells, self._voronoi_edges = [], []
        seeds = [self.project(point) for point in world.voronoi_seeds]
        palette = world.VORONOI_PALETTE
        for index, polygon in enumerate(geometry):
            if len(polygon) < 3:
                continue
            points = [self.project(point) for point in polygon]
            center = seeds[index]
            area = sum(a.cross(b) for a, b in zip(points, points[1:] + points[:1]))
            sign = 1 if area >= 0 else -1
            segments = [(a, b, b - a) for a, b in zip(points, points[1:] + points[:1])]
            self._voronoi_cells.append((center, segments, sign, palette[index % len(palette)]))
        for index, (a, b) in enumerate(world.voronoi_edges):
            start, end = self.project(a), self.project(b)
            middle = (start + end) / 2
            center = min(seeds, key=lambda point: (point - middle).length_squared)
            direction = end - start
            self._voronoi_edges.append((start, end, direction, center, palette[(index * 3) % len(palette)]))

    def voronoi_arcs(self, center, segments, sign, radius, color):
        """Arcos exactos del frente circular, recortados a su celda convexa.

        Solo se dibujan intervalos visibles entre intersecciones circulo/arista;
        no se crean mascaras ni superficies grandes en cada fotograma.
        """
        if radius < 1:
            return
        angles = [0.0, math.tau]
        for a, _b, direction in segments:
            offset = a - center
            length2 = direction.length_squared
            if length2 < 1e-10:
                continue
            projection = -offset.dot(direction) / length2
            closest = offset + direction * projection
            discriminant = (radius * radius - closest.length_squared) / length2
            if discriminant < 0:
                continue
            delta = math.sqrt(discriminant)
            for parameter in (projection - delta, projection + delta):
                if 0 <= parameter <= 1:
                    point = offset + direction * parameter
                    angles.append(math.atan2(point.y, point.x) % math.tau)
        angles.sort()
        for start, end in zip(angles, angles[1:]):
            if end - start < 1e-5:
                continue
            middle = (start + end) / 2
            sample = center + V(math.cos(middle), math.sin(middle)) * radius
            if any(sign * direction.cross(sample - a) < -1e-4 for a, _b, direction in segments):
                continue
            # Error de cuerda inferior a un quinto de pixel, tambien con radios
            # grandes; las tuplas evitan crear miles de vectores por fotograma.
            count = max(2, min(256, math.ceil((end - start) * math.sqrt(radius / 1.2))))
            step = (end - start) / count
            points = [(center.x + math.cos(start + step * i) * radius,
                       center.y + math.sin(start + step * i) * radius) for i in range(count + 1)]
            pygame.draw.lines(self.canvas, self.shade(color, 0.10), False, points, 7)
            pygame.draw.lines(self.canvas, self.shade(color, 0.31), False, points, 3)
            pygame.draw.aalines(self.canvas, self.shade(color, 0.95), False, points)

    def draw_voronoi(self, world):
        phase = getattr(world, "voronoi_phase", None)
        if phase is None:
            return
        color = POWERUPS["voronoi"][2]
        elapsed = world.voronoi_phase_elapsed
        opacity = clamp(1 - elapsed / world.VORONOI_FADE_DURATION, 0, 1) if phase == "fade" else 1.0
        palette = world.VORONOI_PALETTE
        if phase != "marking":
            self.prepare_voronoi(world)
            radius = world.voronoi_radius * DRAW_SCALE
            if phase == "growth":
                for center, segments, sign, tint in self._voronoi_cells:
                    self.voronoi_arcs(center, segments, sign, radius, tint)
            flash = math.exp(-elapsed * 6) if phase == "pulse" else 0.0
            for index, (a, b, direction, center, tint) in enumerate(self._voronoi_edges):
                if phase == "growth":
                    length2 = direction.length_squared
                    if length2 < 1e-10:
                        continue
                    projection = (center - a).dot(direction) / length2
                    closest = a + direction * projection
                    discriminant = (radius * radius - (closest - center).length_squared) / length2
                    if discriminant <= 0:
                        continue
                    delta = math.sqrt(discriminant)
                    low, high = max(0, projection - delta), min(1, projection + delta)
                    if low >= high:
                        continue
                    start, end = a + direction * low, a + direction * high
                else:
                    start, end = a, b
                strength = opacity * (0.85 + flash * 0.15)
                for width, glow in ((10, 0.1), (5, 0.23), (2, 0.65)):
                    pygame.draw.line(self.canvas, self.shade(tint, strength * glow), start, end, width)
                # White cores flare only at discharge; the jewel colours remain
                # visible around the core and across the finished diagram.
                core = tuple(round(tint[i] + (INK[i] - tint[i]) * flash) for i in range(3))
                pygame.draw.aaline(self.canvas, self.shade(core, strength), start, end)
                if phase == "pulse":
                    travel = clamp(elapsed / 0.5, 0, 1)
                    point = start + (end - start) * (travel if index % 2 else 1 - travel)
                    self.halo(point, tint, 16)
                    pygame.draw.circle(self.canvas, self.shade(INK, opacity), point, 2)
        for index, point in enumerate(world.voronoi_seeds):
            center = self.project(point)
            tint = palette[index % len(palette)]
            age = max(0.0, world.voronoi_elapsed - (index + 1))
            strength = opacity * (0.75 if phase == "marking" else 0.45)
            self.halo(center, tint, 19)
            pygame.draw.line(self.canvas, self.shade(tint, strength), center - V(5, 5), center + V(5, 5), 1)
            pygame.draw.line(self.canvas, self.shade(tint, strength), center - V(5, -5), center + V(5, -5), 1)
            pygame.draw.circle(self.canvas, self.shade(INK, opacity), center, 2)
            if age < 0.65:
                pygame.draw.circle(self.canvas, self.shade(tint, (1 - age / 0.65) * 0.6),
                                   center, round(7 + age * 42), 1)
        for index, target in enumerate(world.voronoi_ghost_targets):
            center = self.project(target.position)
            appearance = clamp(world.voronoi_elapsed * 3 - index * 0.09, 0, 1)
            strength = opacity * appearance
            radius = target.radius * DRAW_SCALE
            if not target.alive:
                age = max(0.0, world.voronoi_elapsed - target.broken_at)
                linger = world.VORONOI_PULSE_DURATION + world.VORONOI_FADE_DURATION
                strength = appearance * clamp(1 - (age / linger) ** 2, 0, 1)
                tint = world.VORONOI_HIT_COLOR
                self.halo(center, tint, 48)
                # Six identifiable pieces fly out; the empty centre retains a
                # bright score marker through both pulse and fade animations.
                for shard in range(6):
                    direction = V(1, 0).rotated(shard * math.tau / 6)
                    normal = V(-direction.y, direction.x)
                    tip = center + direction * (radius + age * 37)
                    triangle = (tip + direction * 7, tip - direction * 4 + normal * 4,
                                tip - direction * 4 - normal * 4)
                    pygame.draw.polygon(self.canvas, self.shade(tint, strength * .65), triangle)
                    pygame.draw.aalines(self.canvas, self.shade((255, 193, 178), strength), True, triangle)
                pygame.draw.circle(self.canvas, self.shade(tint, strength * .6), center,
                                   max(1, round(radius + age * 22)), 2)
                self.label('+1', (center.x, center.y - age * 14), 24,
                           self.shade((255, 216, 190), strength), True)
                continue
            tint = (183, 199, 246)
            if target.predicted_hit:
                tint = world.VORONOI_HIT_COLOR
                strength *= .83 + .17 * math.sin(world.sim_time * 9 + index)
                self.halo(center, tint, 43)
                pygame.draw.circle(self.canvas, self.shade(tint, .12), center, round(radius + 2))
                self.label('HIT', (center.x, center.y + radius + 15), 14, tint, True)
                for corner in range(4):
                    direction = V(1, 0).rotated(math.pi / 4 + corner * math.pi / 2)
                    normal = V(-direction.y, direction.x)
                    point = center + direction * (radius + 8)
                    pygame.draw.lines(self.canvas, self.shade(tint, strength), False,
                                      (point + normal * 4 - direction * 3, point + direction * 2,
                                       point - normal * 4 - direction * 3), 2)
            radius += math.sin(world.sim_time * 2.2 + index) * 1.3
            vertices = [center + V(math.cos(i * math.tau / 6), math.sin(i * math.tau / 6)) * radius
                        for i in range(6)]
            for a, b in zip(vertices, vertices[1:] + vertices[:1]):
                start, end = a + (b - a) * .12, b - (b - a) * .12
                if target.predicted_hit:
                    pygame.draw.line(self.canvas, self.shade(tint, strength * .32), start, end, 5)
                    pygame.draw.line(self.canvas, self.shade(tint, strength), start, end, 2)
                pygame.draw.aaline(self.canvas, self.shade(tint, strength * .95), start, end)
            pygame.draw.circle(self.canvas, self.shade(tint, strength * 0.18), center, max(1, round(radius - 5)), 1)
            pygame.draw.circle(self.canvas, self.shade(tint, strength * 0.7), center, 2)
            for angle in (world.sim_time * 0.7 + index, world.sim_time * 0.7 + index + math.pi):
                glint = center + V(math.cos(angle), math.sin(angle)) * (radius + 5)
                pygame.draw.circle(self.canvas, self.shade(tint, strength * 0.45), glint, 1)

    def draw_fusion(self, world):
        progress = world.fusion_progress
        if progress is None:
            return
        color = POWERUPS["fission"][2]
        for center in world.fusion_centers.values():
            point = self.project(center)
            self.halo(point, color, 70)
            radius = max(5, round(46 * (1 - progress) + 8))
            pygame.draw.circle(self.canvas, self.shade(color, 0.32 + progress * 0.36), point, radius, 1)
            pygame.draw.circle(self.canvas, INK, point, 2 + round(progress * 3))
        stride = max(1, len(world.balls) // 28)
        for ball in world.balls[::stride]:
            if ball.fission_group in world.fusion_centers:
                center = self.project(world.fusion_centers[ball.fission_group])
                pygame.draw.aaline(self.canvas, self.shade(color, 0.15), self.project(ball.body.position), center)

    def draw_charge(self, world, alpha):
        carrier = world.explosion_carrier
        if world.active != "explosion" or world.active_left <= 0 or carrier is None:
            return
        pos = self.project(carrier.previous * (1 - alpha) + carrier.body.position * alpha)
        color = POWERUPS["explosion"][2]
        progress = clamp(1 - world.active_left / 3.0, 0.0, 1.0)
        radius = carrier.radius * DRAW_SCALE + 15 + 12 * progress
        self.halo(pos, color, 64)
        pygame.draw.circle(self.canvas, self.shade(color, 0.25), pos, round(radius - 4), 1)
        for tick in range(48):
            direction = V(0, -1).rotated(tick * math.tau / 48)
            strength = 0.95 if tick < math.ceil(progress * 48) else 0.2
            start = pos + direction * radius
            end = pos + direction * (radius + (10 if tick % 4 == 0 else 6))
            pygame.draw.line(self.canvas, self.shade(color, strength), start, end, 2 if tick % 4 == 0 else 1)
        count = str(max(1, math.ceil(world.active_left - 1e-9)))
        self.label(count, (pos.x, pos.y - radius - 23), 24, color, True)

    def draw_pickup(self, world):
        pick = world.pickup
        color = POWERUPS[pick.kind][2]
        center = self.project(pick.position)
        radius = PICKUP_RADIUS * DRAW_SCALE
        pulse = (math.sin(world.sim_time * 3.5) + 1) / 2
        pygame.draw.circle(self.canvas, self.shade(color, 0.14 + pulse * 0.09),
                           center, round(radius + 10 + 3 * pulse), 1)
        # Shared enamel emblem; the outer star matches the exact collector.
        self._visual_time = world.sim_time
        self.draw_power_symbol(pick.kind, center, color, radius)
        if pick.kind == 'double':
            for index in range(8):
                angle = index * math.tau / 8 - world.sim_time * .23
                direction = V(math.cos(angle), math.sin(angle))
                pygame.draw.aaline(self.canvas, self.shade(GOLD, .32 + pulse * .2),
                                    center + direction * (radius + 6), center + direction * (radius + 9))
        for index in range(3):
            phase = world.sim_time * 0.6 + index * math.tau / 3
            glint = center + V(math.cos(phase), math.sin(phase)) * (radius + 14)
            ray = 2 + int(2 * (math.sin(world.sim_time * 5 + index) + 1) / 2)
            pygame.draw.line(self.canvas, self.shade(color, 0.65), glint - V(ray, 0), glint + V(ray, 0))
            pygame.draw.line(self.canvas, self.shade(color, 0.65), glint - V(0, ray), glint + V(0, ray))
        label = self.text(POWERUPS[pick.kind][0], 14, color)
        x = clamp(center.x, LEFT * DRAW_SCALE + label.get_width() / 2 + 8,
                  RIGHT * DRAW_SCALE - label.get_width() / 2 - 8)
        self.canvas.blit(label, label.get_rect(center=(x, center.y + radius + 26)))

    def draw(self, world, alpha, buttons, mouse, fps_limit, actual_fps, paused):
        s = self.canvas
        self._visual_time = world.sim_time
        s.blit(self.background, (0, 0))
        self.label("NEON / REBOUND", (60, 34), 24, CYAN)
        self.label("TARGETS / POWERUPS", (61, 72), 14, MUTED)
        self.fitted_label(score_text(world.score), (366, 51), 140, 34)
        self.label("SCORE", (332, 73), 14, MUTED)
        self.label('THRUST / L-RIGHT' if world.active == 'drone' else f"MOVEMENT {world.hspeed:02d}", (900, 31), 16, MUTED)
        self.label('ROLL / A-D' if world.active == 'drone' else f"ROTATION {world.aspeed:02d}", (1100, 31), 16, MUTED)
        self.label(f"{actual_fps:03.0f} FPS", (1430, 31), 18, CYAN)
        self.label(f"LIMIT {fps_limit}", (1430, 58), 14, MUTED)
        self.label("EFFECT", (780, 45), 14, MUTED, True)
        effect_text = {kind: details[0] for kind, details in POWERUPS.items()}
        effect_text.update(duality='DUALITY', timewarp='FUTURE ECHO', fission='FISSION',
                           double=multiplier_text(world.score_multiplier))
        effect_color = POWERUPS[world.active][2] if world.active else MUTED
        effect_label = "FUSION" if world.fusion_progress is not None else effect_text.get(world.active, "--")
        self.fitted_label(effect_label, (780, 73), 174, 16, effect_color)
        if world.active == 'drone':
            self.label('READY' if world.drone_waiting else f'{world.active_left:04.1f}s',
                       (780, 95), 14, DRONE_ACCENT, True)
        for button in buttons:
            if button.action == "ball" and not world.secret_unlocked:
                continue
            if world.active == 'drone' and button.action in ('h-', 'h+', 'a-', 'a+'):
                continue
            if button.action == 'powerups':
                over = mouse is not None and button.rect.collidepoint(mouse)
                center = V(button.rect.x + 25, button.rect.centery)
                self.star(center, 21 if over else 19, GOLD if over else self.shade(GOLD, .75))
                self.star(center, 9, INK)
                self.label('POWERUPS', (button.rect.x + 52, button.rect.y + 10), 16, GOLD)
                continue
            hovered = mouse is not None and button.rect.collidepoint(mouse)
            disabled = world.active in ('drone', 'analytical') and button.action in ('ball', 'skip', 'h-', 'h+', 'a-', 'a+')
            hovered = hovered and not disabled
            cooling = button.action == 'skip' and world.skip_ready_at > world.sim_time + 1e-9
            label = f'{math.ceil(world.skip_ready_at - world.sim_time - 1e-9)}s' if cooling else button.label
            pygame.draw.rect(s, (32, 64, 77) if hovered else (23, 37, 56), button.rect, border_radius=7)
            pygame.draw.rect(s, CYAN if hovered else (45, 65, 85), button.rect, 1, border_radius=7)
            self.label(label, button.rect.center, 16, MUTED if cooling or disabled else INK, True)
        self.draw_portals(world)
        # Clip de geometria/particulas: halos y proyectiles nunca invaden la interfaz.
        s.set_clip(pygame.Rect(round(LEFT * DRAW_SCALE + 3), round(TOP * DRAW_SCALE + 3),
                              round((RIGHT - LEFT) * DRAW_SCALE - 6), round((BOTTOM - TOP) * DRAW_SCALE - 6)))
        self.draw_snell(world)
        self.draw_wormhole(world)
        self.draw_drone_background(world)
        self.draw_gaussian(world, alpha)
        self.draw_analytical_background(world)
        if world.active == "satellite":
            self.draw_satellite(world)
        self.draw_voronoi(world)
        self.draw_fortune(world)
        self.draw_quantum(world)
        if world.fusion_progress is not None:
            self.draw_fusion(world)
        if world.ghosts:
            self.draw_ghosts(world, alpha)
        ball_color = COLORS[world.ball_color]
        sparse = len(world.balls) > (20 if world.trail_style in (5, 6, 7, 8) else 80)
        for ball in world.balls:
            pos = self.project(ball.previous * (1 - alpha) + ball.body.position * alpha)
            radius = ball.radius * DRAW_SCALE
            color = POWERUPS["fission"][2] if ball.fission_group is not None else ball_color
            if getattr(ball, 'quantum_charge', 0):
                color = QUANTUM_COLORS[ball.quantum_charge]
            aura = POWERUPS[world.active][2] if world.active else color
            if radius >= math.hypot(WIDTH, HEIGHT):
                s.fill(self.shade(color, .34), s.get_clip())
                continue
            if ball.wave_active and world.trail_style != 4:
                self.draw_wave_trail(ball.trail, pos, POWERUPS["duality"][2], sparse)
            else:
                self.draw_trail(ball.trail, pos, min(radius, 48), color, world.trail_style, sparse)
            if self.draw_drone_body(world, ball, pos, radius, alpha):
                continue
            if getattr(ball, "wormhole_transit", False):
                self.halo(pos, (126, 218, 255), 36)
                pygame.draw.circle(s, self.shade((161, 176, 255), .75), pos, max(1, round(radius + 8)), 1)
                for orbit in (0, math.pi):
                    point = pos + V(math.cos(world.sim_time * 8 + orbit),
                                    math.sin(world.sim_time * 8 + orbit)) * (radius + 8)
                    pygame.draw.circle(s, INK, point, 1)
            pygame.draw.circle(s, self.shade(aura, 0.18), pos, round(radius + 4))
            pygame.draw.circle(s, color, pos, max(1, round(radius)))
            if ball.temporary:
                pygame.draw.circle(s, INK, pos, max(1, round(radius)), 1)
            pygame.draw.circle(s, INK, pos - V(radius * 0.28, radius * 0.3), max(1, round(radius * 0.23)))
            self.draw_quantum_electron(world, ball, pos, radius)
        for projectile in world.projectiles:
            pos = self.project(projectile.previous * (1 - alpha) + projectile.position * alpha)
            if getattr(projectile, "rainbow", False):
                self.draw_rainbow_projectile(projectile, pos, world.trail_style)
                continue
            color = projectile.color
            self.draw_trail(projectile.trail, pos, projectile.radius * DRAW_SCALE, color, world.trail_style)
            pygame.draw.circle(s, self.shade(color, 0.2), pos, round(projectile.radius * DRAW_SCALE + 4))
            pygame.draw.circle(s, color, pos, max(1, round(projectile.radius * DRAW_SCALE)))
            pygame.draw.circle(s, INK, pos, 2)
        p = self.project(world.previous_paddle * (1 - alpha) + world.paddle.position * alpha)
        angle = world.previous_angle * (1 - alpha) + world.paddle.angle * alpha
        polygon = [p + V(*point).rotated(angle) * DRAW_SCALE for point in PADDLE_VERTICES]
        # El borde afilado que se dibuja coincide con el poligono fisico de la pala.
        pygame.draw.polygon(s, self.shade(CYAN, 0.22), [p + (point - p) * 1.05 for point in polygon])
        pygame.draw.polygon(s, CYAN, polygon)
        pygame.draw.aalines(s, INK, True, polygon)
        pygame.draw.circle(s, INK, p, 8)
        pygame.draw.circle(s, BG, p, 4)
        tc = self.TARGET_COLORS[world.target_style]
        tr = max(1, round(TARGET_RADIUS * DRAW_SCALE))
        targets = world.active_targets() if hasattr(world, "active_targets") else ((0, world.target),)
        for target_index, target_position in targets:
            if world.active == 'analytical' and target_index > 0:
                continue
            target = self.project(target_position)
            self.draw_target(world, target_position, target_index)
            if world.active == "snell":
                for index, tint in enumerate(((170, 149, 255), (119, 231, 255), (255, 194, 153))):
                    phase = index * math.tau / 3 + world.sim_time * .6 + target_index
                    glint = target + V(math.cos(phase), math.sin(phase)) * (tr + 8)
                    pygame.draw.circle(s, tint, glint, 2)
            if world.active == "double":
                self.fitted_label(multiplier_text(world.score_multiplier), (target.x, target.y + tr + 18), 180, 14, GOLD)
        if world.pickup:
            self.draw_pickup(world)
        for x, y, age, color in world.rings:
            faded = self.shade(color, max(0, 1 - age / 0.5))
            pygame.draw.circle(s, faded, self.project((x, y)), round((12 + age * 150) * DRAW_SCALE), 2)
        for x, y, vx, vy, life, total, color in world.particles:
            ratio = life / total
            pygame.draw.circle(s, self.shade(color, ratio), self.project((x, y)), max(1, round(3 * ratio)))
        self.draw_charge(world, alpha)
        self.draw_drone_debris(world)
        self.draw_drone_ordnance(world, alpha)
        self.draw_analytical_phantoms(world)
        self.draw_analytical_overlay(world, mouse)
        s.set_clip(None)
        if world.active and world.active not in ('gaussian', 'analytical', 'drone'):
            # La trama y las predicciones pueden pasar por detras del indicador.
            s.blit(self.status_overlay, (WIDTH // 2 - 270, 146))
            title, _, color = POWERUPS[world.active]
            if world.active == "explosion":
                status = f"DETONATION IN {world.active_left:03.1f}s" if world.active_left > 0 else "SHOCKWAVE"
                duration = 3.0
            elif world.fusion_progress is not None:
                status = "NUCLEAR FUSION"
                duration = POWER_DURATION
            elif world.active == "voronoi":
                phase = world.voronoi_phase
                if phase == "marking":
                    ghosts = sum(target.alive for target in world.voronoi_ghost_targets)
                    status = f"VORONOI  {world.active_left:04.1f}s  /  {ghosts} PHANTOMS"
                else:
                    status = {"growth": "VORONOI / WAVEFRONTS",
                              "pulse": "VORONOI / FRACTURE", "fade": "VORONOI / DISSOLVE"}.get(phase, "VORONOI")
                duration = POWER_DURATION
            else:
                status = f"{title}  {world.active_left:04.1f}s"
                duration = POWER_DURATION
            self.label(status, (WIDTH // 2, 171), 20, color, True)
            pygame.draw.rect(s, (30, 40, 57), (600, 200, 400, 5), border_radius=2)
            remaining = round(400 * clamp(world.active_left / duration, 0, 1))
            if world.fusion_progress is not None:
                remaining = round(400 * clamp(world.fusion_progress, 0, 1))
            if world.active == "voronoi" and world.voronoi_phase != "marking":
                phase = world.voronoi_phase
                if phase == "growth":
                    progress = world.voronoi_radius / max(1.0, world.voronoi_max_radius)
                elif phase == "pulse":
                    progress = 1.0
                else:
                    progress = 1 - world.voronoi_phase_elapsed / world.VORONOI_FADE_DURATION
                remaining = round(400 * clamp(progress, 0, 1))
            if remaining:
                pygame.draw.rect(s, color, (600, 200, remaining, 5), border_radius=2)
        elif world.active is None and world.message_left > 0:
            self.label(world.message, (WIDTH // 2, 170), 18, MUTED, True)
        controls_hint = "A/D MOVE   J/L or ARROWS TURN   P PAUSE   R RESTART   F FPS   ESC EXIT"
        if world.active == 'drone':
            controls_hint = "L / RIGHT: THRUST   A/D ROLL   LEFT: BOMB   P PAUSE   R RESTART   ESC EXIT"
        elif world.active == 'gaussian':
            controls_hint = "A/D MOVE / AIM   J/L or ARROWS TURN   P PAUSE   R RESTART   ESC EXIT"
        elif world.active == 'analytical':
            controls_hint = "TYPE f(x)   ENTER: TRACE   CTRL+A: REPLACE   CTRL+P: PAUSE   ESC EXIT"
        self.label(controls_hint, (60, 829), 14, INK)
        self.label(f"{len(world.balls):02d} BALLS    COLLISIONS ON    60 / 120 / 240 / 360 FPS", (60, 853), 14, MUTED)
        self.label("BALL", (1088, 849), 14, ball_color, True)
        self.label("TARGET", (1253, 837), 10, MUTED, True)
        self.fitted_label(TARGET_STYLES[world.target_style], (1253, 856), 103, 14, tc)
        self.label(TRAIL_STYLES[world.trail_style], (1449, 849), 14, CYAN, True)
        if paused:
            s.blit(self.pause_overlay, (0, 0))
            self.label("PAUSED", (WIDTH // 2, 400), 34, CYAN, True)
            self.label("Press P to continue", (WIDTH // 2, 450), 20, INK, True)
        return s


class App:
    def __init__(self, fps=120, seed=None, profile_path=None):
        pygame.init()
        pygame.display.set_caption("Neon Rebound v10 | A/D move - J/L or arrows turn")
        icon_path = resource_path("neon_rebound_icon.png")
        if icon_path.is_file():
            try:
                pygame.display.set_icon(pygame.image.load(str(icon_path)))
            except pygame.error:
                pass
        desktop = pygame.display.get_desktop_sizes()[0]
        scale = min(1.0, (desktop[0] - 80) / WIDTH, (desktop[1] - 100) / HEIGHT)
        size = (max(640, int(WIDTH * scale)), max(360, int(HEIGHT * scale)))
        self.screen = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.renderer = Renderer()
        self.world = World(seed)
        if profile_path is False:
            self.profile_path = None
        else:
            self.profile_path = Path(profile_path or os.environ.get('NEON_REBOUND_PROFILE') or
                                     Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) /
                                     'NeonRebound' / 'discoveries.json')
        self._saved_discoveries = set()
        self.load_discoveries()
        self.sim_clock = SimulationClock()
        self.clock = pygame.time.Clock()
        self.fps_limit, self.paused, self.running = fps, False, True
        self.modal, self.modal_was_paused = None, False
        self.pending_setting = None
        self.text_entry_active = False
        self.measured_fps, self.fps_elapsed, self.fps_frames = 0.0, 0.0, 0
        self.scaled = None
        self.buttons = [
            Button(pygame.Rect(446, 42, 114, 48), "+ BALL", "ball"),
            Button(pygame.Rect(572, 42, 114, 48), "SKIP -1", "skip"),
            Button(pygame.Rect(900, 60, 44, 30), "-", "h-"),
            Button(pygame.Rect(952, 60, 44, 30), "+", "h+"),
            Button(pygame.Rect(1100, 60, 44, 30), "-", "a-"),
            Button(pygame.Rect(1152, 60, 44, 30), "+", "a+"),
            Button(pygame.Rect(1260, 42, 118, 48), "PAUSE", "pause"),
            Button(pygame.Rect(842, 831, 164, 38), "POWERUPS", "powerups"),
            Button(pygame.Rect(1018, 830, 28, 38), "<", "bc-"),
            Button(pygame.Rect(1130, 830, 28, 38), ">", "bc+"),
            Button(pygame.Rect(1170, 830, 28, 38), "<", "tc-"),
            Button(pygame.Rect(1310, 830, 28, 38), ">", "tc+"),
            Button(pygame.Rect(1350, 830, 28, 38), "<", "trail-"),
            Button(pygame.Rect(1520, 830, 28, 38), ">", "trail+"),
        ]

    def load_discoveries(self):
        if self.profile_path is None:
            return
        try:
            data = json.loads(self.profile_path.read_text(encoding='utf-8'))
            known = data.get('discovered', []) if isinstance(data, dict) else []
            if isinstance(known, list):
                self.world.discovered.update(item for item in known if isinstance(item, str) and item in POWERUPS)
            self._saved_discoveries = set(self.world.discovered)
        except (OSError, ValueError):
            pass

    def save_discoveries(self):
        if self.profile_path is None or self.world.discovered == self._saved_discoveries:
            return
        try:
            self.profile_path.parent.mkdir(parents=True, exist_ok=True)
            data = {'version': 1, 'discovered': sorted(self.world.discovered)}
            temporary = self.profile_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
            temporary.replace(self.profile_path)
            self._saved_discoveries = set(self.world.discovered)
        except OSError:
            # A read-only profile must never interrupt a game.
            pass

    def modal_buttons(self):
        if self.modal == 'powerups':
            return [Button(pygame.Rect(1280, 156, 130, 44), 'CLOSE', 'cancel')]
        if self.modal:
            return [Button(pygame.Rect(580, 513, 192, 48), 'CANCEL', 'cancel'),
                    Button(pygame.Rect(800, 513, 220, 48),
                           'EXIT GAME' if self.modal == 'quit' else 'APPLY & RESET' if self.modal == 'setting' else 'RESTART', 'confirm')]
        return []

    def open_modal(self, kind):
        if self.modal is None:
            self.modal_was_paused = self.paused
        self.modal, self.paused = kind, True
        self.sim_clock.accumulator = 0.0
        self.sync_render()

    def close_modal(self):
        self.pending_setting = None
        self.modal, self.paused = None, self.modal_was_paused
        self.sim_clock.accumulator = 0.0
        self.sync_render()

    def confirm_modal(self):
        if self.modal == 'quit':
            self.save_discoveries()
            self.running = False
        elif self.modal == 'setting':
            if self.pending_setting is not None:
                field, value = self.pending_setting
                setattr(self.world, field, value)
                self.world.score = 0
            self.close_modal()
        elif self.modal == 'restart':
            previous = self.world
            self.world = World()
            self.world.discovered = set(previous.discovered)
            self.world.secret_unlocked = previous.secret_unlocked
            self.world.trail_style = previous.trail_style
            self.world.ball_color, self.world.target_color = previous.ball_color, previous.target_color
            self.world.target_style = previous.target_style
            self.world.hspeed, self.world.aspeed = previous.hspeed, previous.aspeed
            self.close_modal()

    def modal_action(self, action):
        if action == 'cancel':
            self.close_modal()
        elif action == 'confirm':
            self.confirm_modal()

    def read_controls(self, keys):
        if self.world.active == 'analytical' and self.world.analytical_phase in ('axes', 'edit', 'calculate'):
            return Controls()
        if not self.paused and not self.world.secret_unlocked and all(keys[key] for key in SECRET_KEYS):
            self.world.secret_unlocked = True
            self.world.message, self.world.message_left = "SECRET DISCOVERED: + BALL", 3.0
            self.world.burst(V(SCREEN_WIDTH / 2, TOP + 80), GOLD, 40)
        return controls_from_keys(keys)

    def viewport(self):
        sw, sh = self.screen.get_size()
        scale = min(sw / WIDTH, sh / HEIGHT)
        w, h = max(1, round(WIDTH * scale)), max(1, round(HEIGHT * scale))
        return pygame.Rect((sw - w) // 2, (sh - h) // 2, w, h)

    def mouse_position(self, position):
        rect = self.viewport()
        if not rect.collidepoint(position):
            return None
        return ((position[0] - rect.x) * WIDTH / rect.w, (position[1] - rect.y) * HEIGHT / rect.h)

    def toggle_pause(self):
        if self.modal is not None:
            return
        self.paused = not self.paused
        self.sim_clock.accumulator = 0.0
        self.sync_render()

    def sync_render(self):
        for ball in self.world.balls:
            ball.previous = ball.body.position
        self.world.previous_paddle = self.world.paddle.position
        self.world.previous_angle = self.world.paddle.angle
        if self.world.active == 'gaussian':
            self.world.gaussian_previous = self.world.gaussian_position
        if self.world.drone_collector is not None:
            self.world.drone_previous_angle = self.world.drone_collector.body.angle

    def action(self, action):
        if self.modal is not None:
            return
        if action == 'powerups':
            self.open_modal('powerups')
            return
        if action == "pause":
            self.toggle_pause()
            return
        if self.paused:
            return
        w = self.world
        if w.active in ('drone', 'analytical') and not action.startswith(('bc', 'tc', 'trail')):
            return
        if action == "ball" and w.secret_unlocked:
            w.add_ball()
        elif action == "skip":
            w.skip_target()
        elif action in ('h-', 'h+', 'a-', 'a+'):
            field, maximum = ('hspeed', 15) if action.startswith('h') else ('aspeed', 10)
            value = clamp(getattr(w, field) + (1 if action.endswith('+') else -1), 0, maximum)
            if value != getattr(w, field):
                if w.score != 0:
                    self.pending_setting = (field, value)
                    self.open_modal('setting')
                else:
                    setattr(w, field, value)
        elif action.startswith("bc"):
            w.ball_color = (w.ball_color + (1 if action.endswith("+") else -1)) % len(COLORS)
        elif action.startswith("tc"):
            w.target_style = (w.target_style + (1 if action.endswith("+") else -1)) % len(TARGET_STYLES)
        elif action.startswith("trail"):
            w.trail_style = (w.trail_style + (1 if action.endswith("+") else -1)) % len(TRAIL_STYLES)
            for ball in w.balls:
                ball.trail.clear()

    def events(self):
        editing = (self.world.active == 'analytical' and self.world.analytical_phase in ('axes', 'edit')
                   and not self.paused and self.modal is None)
        if editing != self.text_entry_active:
            (pygame.key.start_text_input if editing else pygame.key.stop_text_input)()
            self.text_entry_active = editing
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.open_modal('quit')
            elif event.type == pygame.WINDOWFOCUSLOST and not self.paused:
                self.toggle_pause()
            elif (not self.paused and self.modal is None
                  and self.world.active == 'analytical'
                  and (event.type != pygame.MOUSEBUTTONDOWN or self.mouse_position(event.pos) is not None)
                  and self.world.handle_analytical_event(event, self.mouse_position(event.pos)
                          if event.type == pygame.MOUSEBUTTONDOWN else None)):
                continue
            elif event.type == pygame.KEYDOWN:
                if self.modal:
                    if event.key == pygame.K_ESCAPE:
                        self.close_modal()
                    elif event.key == pygame.K_RETURN and self.modal != 'powerups':
                        self.confirm_modal()
                    continue
                if (not self.paused and event.key not in (pygame.K_ESCAPE, pygame.K_p, pygame.K_r)
                        and not getattr(event, 'repeat', False)):
                    self.world.release_drone_platform()
                if event.key == pygame.K_ESCAPE:
                    self.open_modal('quit')
                elif event.key == pygame.K_p:
                    self.toggle_pause()
                elif event.key == pygame.K_r:
                    self.open_modal('restart')
                elif event.key == pygame.K_f:
                    choices = (60, 120, 240, 360)
                    self.fps_limit = choices[(choices.index(self.fps_limit) + 1) % len(choices)] if self.fps_limit in choices else 120
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = self.mouse_position(event.pos)
                if pos is not None:
                    for button in self.modal_buttons() if self.modal else self.buttons:
                        if button.action == 'ball' and not self.world.secret_unlocked:
                            continue
                        if button.rect.collidepoint(pos):
                            if self.modal:
                                self.modal_action(button.action)
                            else:
                                self.action(button.action)
                            break

    def render(self):
        image = self.renderer.draw(self.world, self.sim_clock.alpha, self.buttons,
                                   self.mouse_position(pygame.mouse.get_pos()), self.fps_limit,
                                   self.measured_fps, self.paused and self.modal is None)
        if self.modal:
            self.renderer.draw_modal(self, self.mouse_position(pygame.mouse.get_pos()))
        rect = self.viewport()
        if self.scaled is None or self.scaled.get_size() != rect.size:
            self.scaled = pygame.Surface(rect.size).convert()
        self.screen.fill(BG)
        if rect.size == (WIDTH, HEIGHT):
            self.screen.blit(image, rect)
        else:
            pygame.transform.scale(image, rect.size, self.scaled)
            self.screen.blit(self.scaled, rect)
        pygame.display.flip()

    def run(self):
        previous = time.perf_counter()
        try:
            while self.running:
                now = time.perf_counter()
                elapsed, previous = now - previous, now
                was_paused = self.paused
                self.events()
                if not self.running:
                    break
                if not self.paused and not was_paused:
                    keys = pygame.key.get_pressed()
                    self.sim_clock.advance(self.world, elapsed, self.read_controls(keys))
                    self.save_discoveries()
                self.fps_elapsed += elapsed
                self.fps_frames += 1
                if self.fps_elapsed >= 0.25:
                    self.measured_fps = self.fps_frames / self.fps_elapsed
                    self.fps_elapsed, self.fps_frames = 0.0, 0
                self.render()
                # Espera sin bucle ocupado: no monopoliza un nucleo para limitar FPS.
                self.clock.tick(30 if self.paused else self.fps_limit)
        finally:
            self.save_discoveries()
            pygame.quit()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fps", type=int, default=120, help="Render limit, 30 to 1000 (default: 120)")
    parser.add_argument("--seed", type=int, default=None, help="Optional seed for reproducible runs")
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 30 <= args.fps <= 1000:
        parser.error("--fps must be between 30 and 1000")
    app = App(args.fps, args.seed, profile_path=False if args.smoke_test else None)
    if args.smoke_test:
        # Diagnostico del ejecutable: importa DLL, inicializa video/fuentes,
        # ejecuta fisica y renderiza; no requiere interaccion ni reloj real.
        try:
            for _ in range(300):
                app.world.step(Controls(1, 1))
            app.render()
            for index, kind in enumerate(POWERUPS):
                app.world = World(seed=100 + index)
                app.world.activate_powerup(kind)
                if kind == 'fission':
                    app.world.split_ball(app.world.balls[0])
                    app.world.finish_powerup()
                elif kind == 'explosion':
                    app.world.active_left = .02
                elif kind == 'wormhole':
                    ball = app.world.balls[0]
                    app.world.teleport(ball, app.world.wormhole_entry)
                    ball.body.velocity = (400, 0)
                    for _ in range(180):
                        app.world.step(Controls())
                    app.render()
                    for _ in range(780):
                        app.world.step(Controls())
                    if app.world.score < 1:
                        raise RuntimeError('Wormhole no ha alcanzado el objetivo')
                    app.world.finish_powerup()
                    app.render()
                elif kind == 'snell':
                    ball = app.world.balls[0]
                    app.world.teleport(ball, V(740, app.world.snell_line_y - 20))
                    ball.body.velocity = (100, 500)
                    for _ in range(40):
                        app.world.step(Controls())
                    if not getattr(ball, 'snell_crossings', 0):
                        raise RuntimeError('Snell no ha detectado el cruce del cristal')
                    app.render()
                elif kind == 'quantum':
                    first, second = app.world.quantum_pair
                    app.world._quantum_flash(first, second, {})
                    app.render()
                    app.world.finish_powerup()
                    if app.world.quantum_unobserved is None:
                        raise RuntimeError('Quantum observation state was not created')
                    app.world.quantum_observations.append(first)
                    app.world.resolve_quantum_observations()
                    if len(app.world.balls) != 1:
                        raise RuntimeError('Quantum observation did not restore one ball')
                elif kind == 'gaussian':
                    for _ in range(240):
                        app.world.step(Controls(move=1))
                    app.sync_render()
                    app.render()
                    for tick in range(7200):
                        app.world.step(Controls())
                        if tick == 1500:
                            app.sync_render()
                            app.render()
                        if app.world.active is None:
                            break
                    if app.world.active is not None or not app.world.gaussian_paid or app.world.gaussian_runs != 1:
                        raise RuntimeError('Gaussian Roll did not restore the normal game')
                elif kind == 'drone':
                    ball = app.world.drone_collector
                    waiting_position = V(*ball.body.position)
                    for _ in range(40):
                        app.world.step(Controls(throttle=True))
                    if ball.body.position != waiting_position or app.world.active_left != 15:
                        raise RuntimeError('Drone did not wait on its platform')
                    app.render()
                    app.world.teleport(ball, (1000, 500))
                    app.world.release_drone_platform()
                    ball.body.velocity = (0, 0)
                    app.world.drop_drone_bomb()
                    bomb = app.world.drone_bombs[0]
                    bomb.position = V(1000, BOTTOM - 16)
                    bomb.velocity = V(0, 2000)
                    app.world.step_drone_ordnance(.02, {})
                    if len(app.world.drone_shards) != 5:
                        raise RuntimeError('Grenade did not emit five shards')
                    for _ in range(40):
                        app.world.step(Controls(move=1, throttle=True))
                    app.sync_render()
                    app.render()
                    app.world.teleport(ball, (RIGHT - 45, 500))
                    ball.body.velocity = (800, 0)
                    for _ in range(40):
                        app.world.step(Controls())
                        if app.world.active is None:
                            break
                    if app.world.active is not None or ball.radius != BALL_RADIUS:
                        raise RuntimeError('Drone crash did not restore the ball')
                    app.sync_render()
                    app.render()
                elif kind == 'analytical':
                    if len(app.world.analytical_phantoms) != 4:
                        raise RuntimeError('Analytical Path did not create four phantoms')
                    app.world.analytical_direction = -1
                    for _ in range(200):
                        app.world.step()
                    app.sync_render()
                    app.render()
                    if app.world.submit_analytical('1/x'):
                        raise RuntimeError('Analytical Path accepted an undefined origin')
                    app.render()
                    if not app.world.submit_analytical('sin(4x)'):
                        raise RuntimeError('Analytical Path rejected a valid sine')
                    for tick in range(4800):
                        app.world.step()
                        if tick in (120, 300):
                            app.sync_render()
                            app.render()
                        if app.world.active is None:
                            break
                    if app.world.active is not None or app.world.balls[0].body.space is not app.world.space:
                        raise RuntimeError('Analytical Path did not return the ball to physics')
                elif kind == 'voronoi':
                    for _ in range(3600):
                        app.world.step(Controls())
                    for _ in range(2):
                        for _ in range(240):
                            app.world.step(Controls())
                        app.render()
                for _ in range(40):
                    app.world.step(Controls())
                app.render()
            for style in range(len(TARGET_STYLES)):
                app.world.target_style = style
                app.world.trail_style = style % len(TRAIL_STYLES)
                for _ in range(40):
                    app.world.step()
                app.render()
            app.world.discovered.update(POWERUPS)
            app.open_modal('powerups')
            app.render()
            app.close_modal()
            app.open_modal('restart')
            app.render()
            app.confirm_modal()
            app.open_modal('quit')
            app.render()
            app.close_modal()
            app.world.score = 9
            app.action('h+')
            if app.modal != 'setting' or app.world.score != 9:
                raise RuntimeError('Movement changed without score confirmation')
            app.render()
            app.confirm_modal()
            if app.world.score != 0:
                raise RuntimeError('Confirmed setting did not reset the score')
        finally:
            pygame.quit()
        return
    app.run()


if __name__ == "__main__":
    main()
