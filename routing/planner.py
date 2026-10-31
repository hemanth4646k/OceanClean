"""Greedy intercept chain (SRS 3.3): best mass/energy target first, up to 3, each leg planned from
the previous target's predicted position after collecting it."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone

from currents import CurrentField
from drift import Track, predict_track
from energy import CRUISE_MS, dwell_s, leg_energy_kwh
from intercept import HORIZON_S, Intercept, Position, intercept
from oceanclean_common.telemetry import format_ts

MAX_TARGETS = 3
TRACK_SPAN_S = 2 * HORIZON_S  # how far ahead patch drift is predicted for a whole chain
DRIFT_LINE_POINTS = 24


@dataclass(frozen=True)
class PatchObs:
    """A patch as last surveyed; mass 0 means collected."""

    patch_id: str
    ts: float  # survey time, sim epoch seconds
    lat: float
    lon: float
    mass_kg: float
    radius_m: float


@dataclass(frozen=True)
class Target:
    patch: PatchObs
    start_t: float  # when the vessel sets off on this leg
    meet: Intercept
    dwell_s: float
    energy_kwh: float
    drift: tuple[Position, ...]  # predicted patch path, survey position -> intercept point

    @property
    def score(self) -> float:
        return self.patch.mass_kg / self.energy_kwh

    @property
    def leave_t(self) -> float:
        return self.meet.t + self.dwell_s


@dataclass(frozen=True)
class Plan:
    t0: float
    start: Position
    targets: tuple[Target, ...]

    @property
    def energy_kwh(self) -> float:
        return sum(t.energy_kwh for t in self.targets)

    @property
    def mass_kg(self) -> float:
        return sum(t.patch.mass_kg for t in self.targets)


def track_of(field: CurrentField, p: PatchObs, t0: float) -> Track:
    return predict_track(field, p.ts, p.lat, p.lon, max(t0, p.ts) + TRACK_SPAN_S)


def leg(field: CurrentField, t: float, pos: Position, p: PatchObs, track: Track) -> Target | None:
    horizon = min(HORIZON_S, track.t_end - t)
    if horizon <= 0:
        return None
    meet = intercept(field, t, pos, CRUISE_MS, track.at, horizon)
    if meet is None:
        return None
    dwell = dwell_s(p.mass_kg)
    return Target(
        p, t, meet, dwell, leg_energy_kwh(meet.t - t, dwell), drift_line(track, p.ts, meet)
    )


def drift_line(track: Track, t_from: float, meet: Intercept) -> tuple[Position, ...]:
    n = DRIFT_LINE_POINTS
    pts = [track.at(t_from + (meet.t - t_from) * k / n) for k in range(n)]
    return (*pts, (meet.lat, meet.lon))


def plan_chain(
    field: CurrentField,
    t0: float,
    start: Position,
    patches: Iterable[PatchObs],
    max_targets: int = MAX_TARGETS,
) -> Plan:
    live = {p.patch_id: p for p in patches if p.mass_kg > 0}
    tracks = {pid: track_of(field, p, t0) for pid, p in live.items()}
    chosen: list[Target] = []
    t, pos = t0, start
    while live and len(chosen) < max_targets:
        legs = (leg(field, t, pos, p, tracks[p.patch_id]) for p in live.values())
        best = max((lg for lg in legs if lg is not None), key=lambda lg: lg.score, default=None)
        if best is None:
            break
        chosen.append(best)
        del live[best.patch.patch_id]
        t = best.leave_t
        pos = tracks[best.patch.patch_id].at(t)
    return Plan(t0, start, tuple(chosen))


def repredict(
    field: CurrentField,
    t0: float,
    start: Position,
    patch_ids: Iterable[str],
    patches: Mapping[str, PatchObs],
) -> list[Intercept | None]:
    """Intercepts of an existing chain, in its order, from the vessel's current state.

    One entry per patch; None from the first leg that can no longer be reached.
    """
    ids = list(patch_ids)
    out: list[Intercept | None] = []
    t, pos = t0, start
    for pid in ids:
        p = patches[pid]
        track = track_of(field, p, t0)
        lg = leg(field, t, pos, p, track)
        if lg is None:
            break
        out.append(lg.meet)
        t = lg.leave_t
        pos = track.at(t)
    return out + [None] * (len(ids) - len(out))


def _iso(t: float) -> str:
    return format_ts(datetime.fromtimestamp(t, timezone.utc))


def _pt(lat: float, lon: float) -> dict[str, float]:
    return {"lat": round(lat, 6), "lon": round(lon, 6)}


def route_record(plan: Plan) -> dict[str, object]:
    """JSON-ready waypoints/targets and a WKT LineString (lon lat, SRID 4326) for `routes`."""
    waypoints = [{**_pt(*plan.start), "ts": _iso(plan.t0), "kind": "start"}]
    targets = []
    for tg in plan.targets:
        m, p = tg.meet, tg.patch
        waypoints.append(
            {**_pt(m.lat, m.lon), "ts": _iso(m.t), "kind": "target", "patch_id": p.patch_id}
        )
        targets.append(
            {
                "patch_id": p.patch_id,
                "mass_kg": round(p.mass_kg, 1),
                "radius_m": p.radius_m,
                "now": {**_pt(p.lat, p.lon), "ts": _iso(p.ts)},
                "predicted": {**_pt(m.lat, m.lon), "ts": _iso(m.t)},
                "heading_deg": round(m.heading_deg, 1),
                "transit_h": round((m.t - tg.start_t) / 3600, 2),
                "dwell_h": round(tg.dwell_s / 3600, 2),
                "energy_kwh": round(tg.energy_kwh, 1),
                "score_kg_per_kwh": round(tg.score, 3),
                "drift": [[round(a, 6), round(b, 6)] for a, b in tg.drift],
            }
        )
    coords = ", ".join(f"{w['lon']} {w['lat']}" for w in waypoints)
    return {
        "waypoints": waypoints,
        "targets": targets,
        "wkt": f"LINESTRING({coords})",
        "energy_kwh": plan.energy_kwh,
        "mass_kg": plan.mass_kg,
    }


def predicted_targets(targets: Iterable[Mapping]) -> tuple[tuple[str, float, float], ...]:
    """(patch_id, lat, lon) of each target's predicted intercept, which the gate re-checks."""
    return tuple(
        (t["patch_id"], float(t["predicted"]["lat"]), float(t["predicted"]["lon"])) for t in targets
    )
