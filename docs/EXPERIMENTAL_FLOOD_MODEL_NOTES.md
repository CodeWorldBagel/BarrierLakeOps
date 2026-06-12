# Experimental Flood Model Notes

## Current experiment

The directional inundation model currently uses a dam-seeded downstream HAND-like connectivity experiment. It uses `_window_min` to estimate each cell's local valley bottom, scans from the dam seed through finite DEM cells in the downstream half-plane within `reach_km`, then solves `flood_h` by binary-searching the relative height whose reachable `sum(depth * cell_area)` is close to the scenario `volume_m3` value. The legacy MVP model still keeps its original empirical `2 + volume/12` formula for comparison.

A side-slope landslide source is not used for flow bearing because it describes sediment movement toward the dam, not necessarily river flow direction.

- Public input/output matches `estimate_flood`: `lake_id`, `volume_m3`, `centroid_lonlat`, optional `reach_km`; output uses the same top-level keys and polygon properties.
- Downstream is approximated by the half-plane from the dam seed toward the DEM bbox center; this avoids spreading into obvious upstream terrain while still allowing lateral floodplain spread.
- Extent is controlled by the solved `flood_h`, downstream segment order, and a simple capacity limit. `DEFAULT_FLOOD_H_MAX_M` caps the search if the reachable candidate area cannot contain the full scenario volume. The full/partial scenario volume is used directly, without a second outflow-ratio reduction.
- DEM bbox should include the dam with some buffer. If the dam point is just outside the bbox, the implementation clamps to the nearest DEM edge cell, which can bias the dam elevation.

## Model Roles

Use the three model variants as separate views, not as interchangeable outputs.

- `mvp` / `estimate_flood`
  Legacy comparison model. It still uses the empirical `flood_h = 2 + volume_million / 12` formula, then marks cells whose local relative height is within that height. Keep this as the stable baseline while the experimental models change.

- `directional` / `estimate_flood_directional`
  Capacity-distributed inundation model. It solves `flood_h` from DEM capacity, then applies downstream segment filling so limited water volume is distributed from the dam toward downstream reaches. Use this for "where this amount of released water may actually inundate."

- `impact_area` / `estimate_flood_impact_area`
  Possible impact corridor model. It uses the same downstream candidate and solved `flood_h` logic as `directional`, but skips the final capacity-limited segment pruning and unions in `flow_path`. Use this for "places water may pass through or affect," not for final stored-water depth.

In short:

- `directional` = finite water-volume distribution.
- `impact_area` = possible flow-through / affected corridor.
- `mvp` = old baseline for comparison.

## Current Parameters

- `DEFAULT_DIRECTIONAL_RELATIVE_RADIUS`
  Controls the `_window_min` neighborhood used to estimate each cell's local valley bottom. Larger values smooth over more terrain and can connect broader valley bottoms; smaller values preserve local barriers.

- `DEFAULT_DOWNSTREAM_SEGMENT_M`
  Used only by `directional` during capacity-limited filling. Smaller segments make water advance more gradually downstream; larger segments allow broader downstream sorting.

- `DEFAULT_FLOW_PATH_RISE_TOLERANCE_M`
  Used by `impact_area` flow-path tracing. Larger values allow the flow footprint to cross higher DEM bumps; smaller values make the path easier to stop at local high points.

- `DEFAULT_FLOW_PATH_SEARCH_RADIUS_CELLS`
  Used by `impact_area` flow-path tracing. Each step first checks the 8 neighboring cells. If none qualify, it searches outward ring by ring up to this radius. Larger values bridge more DEM gaps but can broaden the flow footprint.

- `DEFAULT_FLOOD_H_MAX_M`
  Caps the DEM capacity solver. If the target volume cannot fit in reachable cells below this height, the solver returns the capped result and the estimated contained volume will be lower than the scenario volume.

## Test Method

`estimate_flood_impact_area(...)` uses the same downstream candidate logic and default reach as `estimate_flood_directional(...)`, but skips the capacity-limited downstream segment pruning and unions in a simple downstream `flow_path` footprint. It is still affected by `volume_m3` through the solved `flood_h`, but should be interpreted as a possible affected corridor rather than a finite stored-water area. It is exposed as `model_variant: "impact_area"` and appears in the frontend as `可能影響範圍`, so it can be compared against the current capacity-distributed inundation area.

## Recommended next experiments

1. Dam bbox buffer check
   Ensure `downstream_dem_bbox` includes the dam point plus a small upstream/north/south buffer. If the dam point is clamped to a DEM edge cell, warn in debug output because the dam elevation may be biased.

2. Relative-window tuning
   Tune `DEFAULT_DIRECTIONAL_RELATIVE_RADIUS`. Larger windows smooth over more local terrain and can connect broader valley bottoms; smaller windows preserve local barriers.

3. Segment tuning
   Tune `DEFAULT_DOWNSTREAM_SEGMENT_M`. Shorter segments make small volumes stop sooner; longer segments behave more like broad downstream sorting.

4. Flood-height cap tuning
   Tune `DEFAULT_FLOOD_H_MAX_M`. If many scenarios hit the cap, either the candidate reach is too small, the local-relative model is too restrictive, or the cap should be raised for exploratory runs.

5. Downstream-only soft filter
   If the all-direction expansion overfills upstream or side basins, add a soft downstream preference based on DEM descent or distance from dam, while still allowing lateral spreading.

6. Debug metadata mode
   Add optional debug output for dam seed row/col/elevation, whether the dam point was clamped, and connected-cell elevation stats. Keep normal public output compatible with `estimate_flood`.
