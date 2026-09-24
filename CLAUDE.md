# CLAUDE.md — ENOUGH × BVRI Map

## What This Is

Single-page interactive Leaflet map showing the overlap between:
- **Active ENOUGH grantee tracts** in Baltimore City (GOC)
- **Baltimore Vacants Reinvestment Initiative (BVRI)** properties — "Vacants to Value" open bid list and DHCD Impact Investment Areas

Requested by Mihir Parikh. Intentionally simple: one grantee-tract layer, one BVRI-points layer, one investment-area polygon layer (off by default).

**Live site:** https://maryland-governors-office-for-children.github.io/enough-bvri-map/
**Source repo:** https://github.com/Maryland-Governors-Office-for-Children/enough-bvri-map

## Repo Structure

```
docs/                    GitHub Pages site (index.html + data/)
  index.html             Single-page Leaflet map
  crosswalk.html         ENOUGH Crosswalk: per-layer overlap breakdown + stacking/gap view
  methodology.html       Per-layer data-source + join-method documentation
  .nojekyll
  data/
    grantee_tracts.geojson         111 active ENOUGH grantee tracts statewide
    grantees.json                  28 grantee organizations with tract counts
    grantee_geoids.json            ENOUGH grantee tract GEOIDs (statewide, legacy, kept for backwards-compat)
    bvri_vacants.geojson           1,192 Vacants to Value properties (Baltimore City, from DHCD ArcGIS)
    bvri_investment_areas.geojson  7 DHCD Impact Investment Area polygons (Baltimore City)
    nmtc_maryland.geojson          587 NMTC-eligible tracts statewide (CDFI Fund)
    oz_designated_maryland.geojson 149 designated Opportunity Zones (2018 TCJA; MD DHCD/Commerce via iMap) + rural flag
    oz2_eligible_maryland.geojson  451 OZ 2.0-eligible tracts (2020–2024 ACS; OpportunityZones.com) w/ MFI ratio + poverty
    ez_maryland.geojson            34 Maryland Enterprise Zones + Focus Areas (MD Commerce via iMap)
    just_communities_maryland.geojson  419 designated Just Communities (MD DHCD via iMap; Just Communities Act of 2024)
    vacant_buildings_baltimore.geojson  ALL 11,523 open Vacant Building Notices citywide; `in_enough:1` on the
                                        4,108 inside grantee tracts (map fades the rest as context)
    vacant_lots_baltimore.geojson       ALL 18,676 vacant lots citywide; `in_enough:1` on the 5,376 in tracts
    vacancy_reductions_baltimore.geojson  7,199 VBN closures since FY25 as points; `durable` flags whether the
                                          property stayed off (2,356 citywide / 833 in ENOUGH did)
    vacancy_change_tracts.geojson        all 199 Baltimore City tracts w/ baseline/now/change + `in_enough`
    vacants_enough.json                vacancy rollup: per-grantee/tract/neighborhood counts + reduction trend,
                                       `reduction_comparison` (ENOUGH vs rest of city, size bins, significance),
                                       `grantee_reduction_rates`, `by_city_tract` (all 199)
    crosswalk.json                 Precomputed ENOUGH × layer overlap (built by build_crosswalk.py)
scripts/
  fetch_bvri.py          Refresh BVRI data from Baltimore City DHCD ArcGIS REST
  fetch_oz2.py           Refresh OZ 2.0-eligible tracts from opportunityzones.com + rural flag on designated OZs
  fetch_ez.py            Refresh Maryland Enterprise Zones from iMap MD_IncentiveZones
  fetch_jc.py            Refresh Just Communities from iMap MD_HousingDesignatedAreas Layer 9
  fetch_vacants.py       Baltimore vacancy inventory (VBN intervals + lots) -> ENOUGH rollup (needs shapely)
  build_crosswalk.py     Compute ENOUGH × layer overlap (Shapely) -> docs/data/crosswalk.json
  requirements-crosswalk.txt  Pinned shapely for build_crosswalk.py
```

## How to Refresh Data

```bash
python3 scripts/fetch_bvri.py   # re-fetches bvri_vacants.geojson + bvri_investment_areas.geojson
python3 scripts/fetch_jc.py     # re-fetches just_communities_maryland.geojson (419 tracts)
.venv-geo/bin/python scripts/fetch_vacants.py   # vacancy inventory + ENOUGH rollup (~3 min)
# then commit the refreshed docs/data/*.geojson
```

BVRI data source: `https://egisdata.baltimorecity.gov/egis/rest/services/Housing/DHCD_Open_Baltimore_Datasets/FeatureServer`
- Layer 7: Vacants to Value (open bid list)
- Layer 10: Impact Investment Areas

ENOUGH grantee tract data is built from the `enough-eligibility-changes` repo. To rebuild after that repo's data updates:
```bash
python3 -c "
import json
src = json.load(open('../enough-eligibility-analysis/docs/data/tracts_2026.geojson'))
geoids = set(json.load(open('docs/data/grantee_geoids.json')))
keep_props = ['GEOID20','F2024_Child_Poverty_Rate__2026_','F2024_Child_Poverty_Rate_Margin_Of_Error','SCHOOL_BND_INT_CPG_TOTAL']
feats = [{'type':'Feature','geometry':f['geometry'],'properties':{k:f['properties'].get(k) for k in keep_props}}
         for f in src['features']
         if f['properties'].get('JURSCODE') == 'BACI' and f['properties'].get('GEOID20') in geoids]
json.dump({'type':'FeatureCollection','features':feats}, open('docs/data/grantee_tracts.geojson','w'))
print(len(feats), 'grantee tracts written')
"
```

After refreshing ANY source layer (grantee tracts or any incentive layer), rebuild the
crosswalk so `crosswalk.json` stays in sync (the map + crosswalk page both read it):
```bash
python3 -m venv .venv-geo && .venv-geo/bin/pip install -r scripts/requirements-crosswalk.txt
.venv-geo/bin/python scripts/build_crosswalk.py          # rebuild docs/data/crosswalk.json
.venv-geo/bin/python scripts/build_crosswalk.py --check   # verify JSON matches source data
```
`build_crosswalk.py` stamps a `source_hash` into the JSON; `--check` fails (exit 1) if the
committed `crosswalk.json` is stale vs. the source geojson. Run it before any external share.

## Deploy

Push to `main` → GitHub Pages auto-deploys from `docs/`.

## Key Numbers (as of May 2026)

- 28 active ENOUGH grantees, 111 grantee tracts statewide. **46** of those tracts, across **11**
  grantee organizations, are in Baltimore City — that 11/46 is the denominator for the two
  Baltimore-City-only layers (BVRI, DHCD Impact Areas), not 28/111. All 11 serve only city tracts.
  `build_crosswalk.py` derives the set from `JURSCODE == 'BACI'` and exposes it as `totals.baltimore_city`
  plus a per-layer `universe` object
- **Baltimore vacancy inventory (the real vacancy universe, added 2026-09-23).** Citywide **11,523 open
  Vacant Building Notices + 18,497 vacant lots = 30,020 total vacants**. Inside ENOUGH grantee tracts:
  **4,108 buildings + 5,362 lots = 9,470 total** — i.e. ENOUGH's 46 Baltimore tracts hold **36% of the
  city's vacant buildings** and 32% of all vacants. Buildings fell from 4,793 at FY25 start to 4,108
  (**−685, −14.3%**) vs citywide −1,703 (−12.9%) — so ENOUGH communities delivered ~40% of the entire
  citywide reduction. Source: DHCD `VacantsTimeSlider` (interval data → stock computable at any date;
  validated within 0.6% of DHCD's Power BI dashboard at every FY boundary) + `VacantLot_Test`.
  **Host note:** Open Baltimore's public [Vacant Building Notices](https://data.baltimorecity.gov/datasets/baltimore::vacant-building-notices/explore)
  dataset is the SAME layer we use (`DHCD_Open_Baltimore_Datasets/FeatureServer/1`) served from `baltegis`
  instead of `egisdata`; its count (11,448) is exactly the dashboard's headline. It has **no history**
  (`DateCancel`/`DateAbate` are non-null 0 times), so it cannot produce any baseline or trend — that needs
  `VacantsTimeSlider`. Three "current" numbers exist (11,448 baltegis / 11,481 egisdata / 11,523 ours from
  intervals); ~0.65% snapshot drift, not a definitional gap. We stay on `egisdata` because it is the only host
  that also publishes the vacant-lot layer. Quote DHCD's dashboard for official figures.
  **Flows since FY25 start (ENOUGH):** 2,201 VBNs closed and 1,789 newly issued — but **1,370 closures were
  followed by a new notice**, so only **~831 were durable**. Quote 831, not 2,201 — a raw closed-notice count
  overstates progress ~2.6×. Re-noticing is **administrative, not re-vacancy**: median gap closure→next notice
  is **5 days**, 89.8% within 30 days, 0.2% beyond a year (audited 2026-09-24). Resolution is
  overwhelmingly preservation: **1,062 rehab permits vs 97 City demolitions (10.9:1**, vs citywide 9.9:1).
  Rehab permits ≠ completions; demolitions are City-funded only. Per-grantee ratio varies a lot
  (Park Heights 13.4:1, Elev8 4.0:1).
  **⚠ Do NOT headline "% of tracts where vacancy fell" (ENOUGH 88.9% vs rest-of-city 77.6%).** The measure
  tracks *starting stock*, not performance: tracts with 150+ vacants fell 100% of the time, tracts with 1–10
  fell 62.7%, and ENOUGH holds **0%** of the smallest band vs **40%** of the largest — it clears a one-building
  bar mechanically. **Indirect standardization settles it:** applying citywide band-specific rates, expected
  41.0 of 45 ENOUGH tracts to fall; 40 did → **ratio 0.975**. Corrected for size, ENOUGH performed *as the rest
  of the city did, not better.* Median per-tract change is *better* outside ENOUGH (−19.8% vs −14.3%), same
  reason in reverse. **No p-value is published** — ENOUGH tracts are purposively selected (poverty ≥30%), not
  sampled, so there is no null to test. **Defensible topline instead:** 36% of the city's
  vacant buildings + ~40% of its net reduction + 10.9:1 repair-to-demolition. Both measures are published
  with the size-bin table so the confound is visible.
  **Never imply ENOUGH caused the reduction** — DHCD and the Vacants Reinvestment Council drive vacancy work;
  no ENOUGH grantee is contracted on vacancy. These are *place* measures, not grantee scorecards.
  **Do not confuse with the BVRI open-bid list below** — that is ~1,200 properties being marketed, not
  the vacancy stock. Lots have no history, so they are excluded from all trend columns.
- 1,192 BVRI **open-bid** properties (Baltimore City only; the slice DHCD is marketing for sale — a
  ~10% subset of the vacant-building stock, not the vacancy measure)
- 7 DHCD Impact Investment Areas (Baltimore City only)
- 587 NMTC-eligible tracts statewide (350 Severe Distress, 237 Distressed)
- 149 designated Opportunity Zones statewide (2018 TCJA, in effect through 2028; 47 rural)
- 451 OZ 2.0-eligible tracts statewide (2020–2024 ACS via opportunityzones.com; MD may nominate up to 113, effective 2027).
  **92** grantee tracts (26/28 communities) are OZ 2.0-eligible — exact-GEOID join
- 419 designated **Just Communities** statewide (Just Communities Act of 2024, HB 241/SB 308; MD DHCD via iMap
  `MD_HousingDesignatedAreas` Layer 9). **81** grantee tracts (26/28 communities) are Just Communities — exact-GEOID
  join. DHCD Methodology **v1.0** (2025-04-23): 4 of 14 legislated criteria had no data; qualifying score ≥13.5 is an
  administrative cutoff, not statutory; results clipped to Priority Funding Areas. A v2.0 will move both counts.
  **Careful with `redlining`:** it is only ever `true` (184) or `null` (235) — never `false`. HOLC mapped only a few
  Maryland cities, so `null` means "no HOLC map here", NOT "not redlined". Never report the complement as un-redlined.
- 32 Maryland Enterprise Zones + 2 Focus Areas statewide; **86** grantee tracts touch an Enterprise Zone
  (any-overlap; headline). A stricter ≥5%-area test gives **71** (footnoted on the crosswalk page — the
  15-tract gap is boundary slivers). EZ uses any-overlap because it has no tract-based ground truth to
  validate a threshold against; OZ keeps 5% because that reproduces its exact-GEOID count. Map reads both
  from `crosswalk.json`.

### ENOUGH Crosswalk overlap (from `crosswalk.json`)
- NMTC: 28/28 communities, 102/111 tracts (86 Severe Distress, 16 Distressed) — every community is NMTC-eligible
- Opportunity Zones (designated): 20/28 communities, 38/111 tracts (≥5% area)
- OZ 2.0-eligible: 26/28 communities, 92/111 tracts (exact GEOID; 20% of the 451-tract eligible pool)
- Enterprise Zones: 21/28 communities, 86/111 tracts (any overlap; 71 at ≥5% area)
- Just Communities: 26/28 communities, 81/111 tracts (exact GEOID; 19% of the 419 statewide). The 30
  non-designated grantee tracts cluster in Prince George's (10) + Anne Arundel (7); Caroline Human Services
  Council and One Annapolis have zero. Excluded from the stacking histogram (funding priority, not a tax credit)
- BVRI Vacants: **10/11 Baltimore City communities, 33/46 Baltimore City tracts** (565 of 1,192
  properties inside a grantee tract). Scored against the city footprint, not statewide — a grantee
  outside Baltimore cannot contain a BVRI property, so a statewide denominator invents a gap
- DHCD Impact Areas: **6/11 Baltimore City communities, 21/46 Baltimore City tracts** (same reason)
- Stacking (statewide NMTC/OZ/EZ, EZ any-overlap): 6 tracts in zero program, 15 in one, 59 in two,
  31 in all three; all 28 communities are in at least one
