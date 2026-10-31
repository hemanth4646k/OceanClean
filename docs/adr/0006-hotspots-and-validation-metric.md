# 0006 Hotspots are persistent 1° convergence cells; validated by median concentration ratio

Status: accepted, 2026-10-31 (M2)

Daily divergence at SCUD's ¼° resolution is dominated by eddy noise, and the 2,310 microplastics samples are too sparse to land in ¼° cells. The batch ETL therefore:

- computes daily divergence per ¼° cell from central neighbour differences on the sphere, `div = [∂u/∂λ + ∂(v cos φ)/∂φ] / (R cos φ)`;
- averages it per day over each 1° cell (at least 8 of 16 sub-cells present), then over the history;
- ranks 1° cells by mean divergence, most negative first. A **hotspot** is a cell in the most convergent quarter that also converged on more than half of the days.

Validation joins NCEI samples to 1° cells, keeping only `pieces/m3` ocean-water samples (every other unit is a beach count). Samples in hotspot cells are compared with samples in all other analysed cells. The headline is the **ratio of medians**. Concentrations are heavy-tailed and many are 0, so a few extreme samples dominate the mean. The ratio of means is computed and stored too, so the demo can show both. These rules were fixed before the full-history result was seen. Samples span decades and the currents span 2 years: the claim is about persistent (climatological) convergence, not the same days.

Other M2 choices:

- The mission window (last 45 days of the mission box) is cut from the history by the ETL rather than fetched separately: the history always ends at the dataset's last day, so this avoids one more network dependency.
- Lake keys follow the medallion names (`bronze/`, `silver/`, `gold/`, defined in `oceanclean_common.regions`) instead of the ticket's `raw/`.
- Closed months are immutable upstream, so a cached closed month is reused without calling ERDDAP; the open month is re-fetched every run.
- ADR-0001's "append-only" covers telemetry history. Batch reference data derived from NOAA is rewritten idempotently instead:
  - The open month's bronze object is replaced while upstream still adds days to it.
  - Silver currents use dynamic partition overwrite, so a re-run rewrites only the dates it produced and older dates stay.
  - Gold views are recomputed in full.

  Each rewrite reproduces the same rows from the same upstream data, so no history is lost.
