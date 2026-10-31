"""One simulator tick: follow the active route, collect, offload, loiter, drift the debris."""

from __future__ import annotations

import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass, field
from datetime import datetime

from currents import CurrentField
from debris import Patch, collect, debris_density, drift_patches
from energy import COLLECT_KN, CRUISE_KN, HOLD_CAPACITY_KG, LOITER_KN
from fuel import burn
from geo import KN_TO_MS, bearing_deg, displacement, distance_m
from intercept import steer_heading
from link import Link
from oceanclean_common.telemetry import Telemetry
from vessel import FUEL_TANK_L, VesselState, step_position

OFFLOAD_S = 6 * 3600.0  # alongside the tender: hold emptied, tank topped up
HOMING_M = 10_000.0  # within this range the crew sees the patch and steers at it directly
LOITER_RADIUS_M = 500.0
SURVEY_EVERY_S = 3600.0

RouteTargets = Sequence[tuple[str, float, float]]  # (patch_id, waypoint lat, waypoint lon)


@dataclass
class World:
    patches: list[Patch]
    mode: str = "loiter"  # transit | collect | loiter | offload | adrift
    offload_until: float = 0.0
    next_survey: float = 0.0
    collected_kg: float = 0.0
    anchor: tuple[float, float] | None = None  # loiter circle centre
    link: Link = field(default_factory=Link)

    def to_dict(self) -> dict[str, object]:
        d = asdict(self)
        d["link"] = {
            "offline_until": self.link.offline_until,
            "queue": [e.to_json() for e in self.link.queue],
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> World:
        link = d["link"]
        queue = [Telemetry.model_validate_json(e) for e in link["queue"]]
        return cls(
            patches=[Patch(**p) for p in d["patches"]],
            mode=d["mode"],
            offload_until=d["offload_until"],
            next_survey=d["next_survey"],
            collected_kg=d["collected_kg"],
            anchor=tuple(d["anchor"]) if d.get("anchor") else None,  # absent before M3 review
            link=Link(link["offline_until"], queue),
        )


def to_telemetry(v: VesselState, ts: datetime, buffered: bool = False) -> Telemetry:
    return Telemetry(
        vessel_id=v.vessel_id,
        event_ts=ts,
        seq=v.seq,
        lat=v.lat,
        lon=v.lon,
        heading_deg=v.heading_deg % 360,
        speed_kn=v.speed_kn,
        battery_pct=v.battery_pct,
        fuel_l=v.fuel_l,
        debris_density=v.debris_density,
        hold_fill_pct=v.hold_fill_pct,
        buffered=buffered,
    )


def waypoint_targets(waypoints: Iterable[Mapping]) -> RouteTargets:
    """(patch_id, lat, lon) of a stored route's target waypoints, which the vessel steers for.

    Waypoints, not the targets' predictions: an operator's Modify (M5) moves a waypoint.
    """
    return tuple(
        (w["patch_id"], float(w["lat"]), float(w["lon"]))
        for w in waypoints
        if w["kind"] == "target"
    )


def loiter_heading(
    pos: tuple[float, float], anchor: tuple[float, float], speed_ms: float, u: float, v: float
) -> float:
    """Circle the anchor clockwise at LOITER_RADIUS_M, crabbing so the current can't carry it off.

    The ground track is the tangent, bent inward when outside the radius and outward inside it.
    """
    r = distance_m(*pos, *anchor)
    if r < 1.0:
        return steer_heading(0.0, speed_ms, u, v)
    to_anchor = bearing_deg(*displacement(*pos, *anchor))
    bend = max(-90.0, min(90.0, 90.0 * (r - LOITER_RADIUS_M) / LOITER_RADIUS_M))
    return steer_heading((to_anchor - 90.0 + bend) % 360.0, speed_ms, u, v)


def next_target(route: RouteTargets | None, patches: dict[str, Patch]) -> tuple[str, float, float]:
    """First route target whose patch still holds debris, or ("", 0, 0) when there is none."""
    for pid, lat, lon in route or ():
        p = patches.get(pid)
        if p is not None and p.mass_kg > 0:
            return pid, lat, lon
    return "", 0.0, 0.0


def steer(
    w: World, v: VesselState, t: float, field: CurrentField, route: RouteTargets | None
) -> tuple[str, float, float]:
    """(mode, heading, speed kn) for the next tick."""
    if v.fuel_l <= 0:
        return "adrift", v.heading_deg, 0.0
    by_id = {p.patch_id: p for p in w.patches}
    pid, wlat, wlon = next_target(route, by_id)
    u, vv = field.uv(t, v.lat, v.lon)
    if not pid:
        anchor = w.anchor or (v.lat, v.lon)
        return (
            "loiter",
            loiter_heading((v.lat, v.lon), anchor, LOITER_KN * KN_TO_MS, u, vv),
            LOITER_KN,
        )
    p = by_id[pid]
    gap = distance_m(v.lat, v.lon, p.lat, p.lon)
    mode, speed = ("collect", COLLECT_KN) if gap <= p.radius_m else ("transit", CRUISE_KN)
    aim = (p.lat, p.lon) if gap < HOMING_M else (wlat, wlon)
    bearing = bearing_deg(*displacement(v.lat, v.lon, *aim))
    return mode, steer_heading(bearing, speed * KN_TO_MS, u, vv), speed


def tick(
    w: World,
    v: VesselState,
    t: float,
    dt: float,
    field: CurrentField,
    route: RouteTargets | None,
    rng: random.Random,
    fuel_factor: float = 1.0,
) -> None:
    """Advance the vessel and the debris world by dt sim seconds starting at sim time t."""
    move_vessel(w, v, t, dt, field, route, fuel_factor)
    drift_patches(w.patches, field, t, dt, rng)
    v.debris_density = debris_density(w.patches, v.lat, v.lon)


def move_vessel(
    w: World,
    v: VesselState,
    t: float,
    dt: float,
    field: CurrentField,
    route: RouteTargets | None,
    fuel_factor: float = 1.0,
) -> None:
    """The vessel's part of a tick: steer, move, collect or offload, burn. Patches stay put."""
    if w.mode == "offload" and t >= w.offload_until:
        v.hold_fill_pct = 0.0
        v.fuel_l = FUEL_TANK_L
        w.mode = "loiter"
    if w.mode == "offload":
        mode, heading, speed = "offload", v.heading_deg, 0.0
    else:
        mode, heading, speed = steer(w, v, t, field, route)
    w.anchor = (w.anchor or (v.lat, v.lon)) if mode == "loiter" else None
    u, vv = field.uv(t, v.lat, v.lon)
    v.lat, v.lon = step_position(v.lat, v.lon, heading, speed * KN_TO_MS, dt, u, vv)
    v.heading_deg, v.speed_kn = heading % 360.0, speed
    if mode == "collect":
        room = HOLD_CAPACITY_KG * (1 - v.hold_fill_pct / 100.0)
        kg = collect(w.patches, v.lat, v.lon, dt, room)
        w.collected_kg += kg
        v.hold_fill_pct = min(100.0, v.hold_fill_pct + kg / HOLD_CAPACITY_KG * 100.0)
        if v.hold_fill_pct >= 100.0 - 1e-9:
            v.hold_fill_pct = 100.0
            mode, w.offload_until = "offload", t + dt + OFFLOAD_S
    burn(v, mode, speed * KN_TO_MS, dt, fuel_factor)
    w.mode = mode
