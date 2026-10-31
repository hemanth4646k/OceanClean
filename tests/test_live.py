from live import Wake, changes

H = 3600.0


def vessel(seq: int, ts: str = "2026-09-01T01:00:00Z") -> dict:
    return {"vessel_id": "OC-01", "seq": seq, "event_ts": ts, "lat": 35.0, "lon": -142.0}


def patch(pid: str, mass: float) -> dict:
    return {"patch_id": pid, "mass_kg": mass, "lat": 35.0, "lon": -142.0}


def route(rid: int, status: str = "pending") -> dict:
    targets = [{"patch_id": "P21"}, {"patch_id": "P06"}]
    return {
        "route_id": rid,
        "status": status,
        "reason": "no_route",
        "mass_kg": 9100.0,
        "targets": targets,
    }


def snap(**over: object) -> dict:
    base = {
        "vessel": vessel(1),
        "patches": [patch("P21", 5000.0)],
        "routes": {"active": None, "pending": None},
        "clock": {"sim_now": "2026-09-01T01:00:00Z", "rate": 60.0, "paused": False},
        "hitl": {"autopilot": True, "timeout_s": 30.0, "deadline": None},
    }
    return {**base, **over}


def test_wake_keeps_points_in_time_order_within_the_age_limit() -> None:
    w = Wake(max_age_s=10 * H)
    for h in range(15):
        w.add(h * H, 35.0 + h, -142.0)
    pts = w.points()
    assert [p[0] for p in pts] == [35.0 + h for h in range(4, 15)]  # 10 h back, inclusive


def test_wake_ignores_repeats_and_restarts_when_sim_time_goes_back() -> None:
    w = Wake(max_age_s=10 * H)
    w.add(5 * H, 35.0, -142.0)
    w.add(5 * H, 35.0, -142.0)  # same poll result twice
    assert len(w.points()) == 1
    w.add(1 * H, 31.0, -140.0)  # a clean sim start reuses earlier sim times
    assert w.points() == [(31.0, -140.0)]


def test_wake_caps_its_length() -> None:
    w = Wake(max_age_s=1e9, max_points=3)
    for i in range(5):
        w.add(float(i), 35.0 + i, -142.0)
    assert [p[0] for p in w.points()] == [37.0, 38.0, 39.0]


def test_only_changed_parts_are_sent() -> None:
    a = snap()
    b = snap(vessel=vessel(2))
    assert changes(a, a) == []
    assert changes(a, b) == [{"type": "vessel", "data": vessel(2)}]


def test_first_poll_sends_everything_without_alerts() -> None:
    msgs = changes(None, snap(routes={"active": None, "pending": route(1)}))
    assert {m["type"] for m in msgs} == {"vessel", "patches", "routes", "clock", "hitl"}


def test_new_proposal_raises_an_alert() -> None:
    b = snap(routes={"active": None, "pending": route(7)})
    alerts = [m["data"] for m in changes(snap(), b) if m["type"] == "alert"]
    assert len(alerts) == 1
    assert "Route 7 proposed" in alerts[0]["text"] and "P21 → P06" in alerts[0]["text"]
    assert alerts[0]["kind"] == "proposal"


def test_accepting_a_proposal_alerts_once_for_the_new_active_route() -> None:
    a = snap(routes={"active": None, "pending": route(7)})
    b = snap(routes={"active": route(7, "active"), "pending": None})
    alerts = [m["data"] for m in changes(a, b) if m["type"] == "alert"]
    assert [x["kind"] for x in alerts] == ["active"]


def test_routes_the_autopilot_accepts_raise_no_alert() -> None:
    # At fast sim rates autopilot decides every few real seconds; the sidebar shows it instead.
    b = snap(routes={"active": {**route(7, "active"), "decided_by": "autopilot"}, "pending": None})
    assert [m for m in changes(snap(), b) if m["type"] == "alert"] == []


def test_collected_patch_raises_an_alert_but_a_partial_haul_does_not() -> None:
    a = snap(patches=[patch("P21", 5000.0), patch("P06", 4000.0)])
    b = snap(patches=[patch("P21", 0.0), patch("P06", 1000.0)])
    alerts = [m["data"] for m in changes(a, b) if m["type"] == "alert"]
    assert [x["kind"] for x in alerts] == ["collected"]
    assert "P21" in alerts[0]["text"]
