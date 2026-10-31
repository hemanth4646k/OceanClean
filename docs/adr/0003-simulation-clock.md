# 0003 Compressed simulation clock drives event time

Status: accepted, 2026-10-31

The demo shows about 30 days of cleanup in minutes. The simulator owns a sim clock (adjustable rate, play/pause) and stamps `event_ts` in sim time. Spark windows, watermarks and dedup use event time only, so compressed time is consistent end to end. Watermark and window sizes are in sim time.
