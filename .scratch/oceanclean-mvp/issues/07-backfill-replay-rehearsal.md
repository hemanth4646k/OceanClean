# 07 (M6) Backfill burst, time-slider replay, rehearsal
Status: open
Blocked by: 06
Estimate: 2 h

## Do
- Simulator `--fast-forward 30d`: ~2.6M ticks burst through ingestion/Kafka; gold telemetry aggregates job.
- Time slider: replay patch drift over a historical window from silver currents.
- Clean-start rehearsal with network off; fix anything flaky. Record 2-min backup video. Update CLAUDE.md Commands + Status.
