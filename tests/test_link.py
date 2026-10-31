import random
from datetime import datetime, timedelta, timezone

from link import MAX_BATCH, Link
from oceanclean_common.telemetry import Telemetry

T = datetime(2026, 9, 1, tzinfo=timezone.utc)


def ev(seq: int) -> Telemetry:
    return Telemetry(
        vessel_id="OC-01",
        event_ts=T + timedelta(minutes=seq),
        seq=seq,
        lat=35.0,
        lon=-142.0,
        heading_deg=0.0,
        speed_kn=6.0,
        battery_pct=90.0,
        fuel_l=1000.0,
        debris_density=0.0,
        hold_fill_pct=0.0,
    )


class Sink:
    def __init__(self, ok: bool = True) -> None:
        self.ok = ok
        self.got: list[Telemetry] = []

    def __call__(self, batch: list[Telemetry]) -> bool:
        if self.ok:
            self.got.extend(batch)
        return self.ok


def test_online_sends_fresh_events_unbuffered() -> None:
    link, sink = Link(), Sink()
    assert link.flush(0.0, [ev(1), ev(2)], sink) == 2
    assert [e.buffered for e in sink.got] == [False, False]
    assert link.queue == []


def test_offline_queues_as_buffered_then_flushes_in_order() -> None:
    link, sink = Link(offline_until=100.0), Sink()
    link.flush(50.0, [ev(1), ev(2)], sink)
    assert sink.got == [] and [e.buffered for e in link.queue] == [True, True]
    link.flush(150.0, [ev(3)], sink)
    assert [(e.seq, e.buffered) for e in sink.got] == [(1, True), (2, True), (3, False)]
    assert link.queue == []


def test_failed_post_keeps_events_for_retry() -> None:
    link = Link()
    link.flush(0.0, [ev(1)], Sink(ok=False))
    assert [(e.seq, e.buffered) for e in link.queue] == [(1, True)]


def test_large_backlog_goes_out_in_batches() -> None:
    link, sizes = Link(offline_until=10.0), []
    link.flush(0.0, [ev(k) for k in range(MAX_BATCH + 5)], Sink())
    link.flush(20.0, [], lambda b: sizes.append(len(b)) or True)
    assert sizes == [MAX_BATCH, 5]


def test_outages_start_at_about_the_configured_rate() -> None:
    link, rng = Link(), random.Random(5)
    starts, t = 0, 0.0
    for _ in range(30 * 24 * 60):  # 30 sim-days of 1-minute ticks
        if link.maybe_drop(t, 60.0, rng):
            starts += 1
            assert not link.online(t + 60.0)
        t += 60.0
    assert 10 <= starts <= 30
