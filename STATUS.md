# ENOUGH × BVRI Map — Status & Open Steps

_Last reviewed: 2026-09-23 (Baltimore vacancy inventory + Vacants Reduction crosswalk added per Mihir;
basemap swapped off CARTO — it now watermarks its tiles "API KEY REQUIRED" — to Esri's keyless Light Gray
Canvas; Baltimore-City-only layers rescoped to a Baltimore City denominator; pushed)._ Living index of what's done, what's open, and what needs a decision.
See `CLAUDE.md` for project context; `docs/methodology.html` for the per-layer data-source documentation.

A GitHub-Pages site (`docs/`) with three pages: a Leaflet **map** showing where active ENOUGH grantee
tracts overlap Baltimore Vacants Reinvestment Initiative (BVRI) activity plus federal/state incentive
layers; an **ENOUGH Crosswalk** page breaking down that overlap program-by-program; and a
**methodology** page. Originally requested by Mihir Parikh; intentionally simple, since expanded.
**Live:** https://maryland-governors-office-for-children.github.io/enough-bvri-map/

## Workstream A — Map build & layers

**Done (2026-09-24) — methodology audit + council re-review; FIXED A LIVE NEGATIVE NUMBER.** A second council
round reviewed my own audit and found three live errors I had missed:
1. **`cycled_properties` was still summing over all 199 tracts** (the same 46→199 universe bug I thought I'd
   fixed in one field), making it larger than `gross_resolved`. The live site was publishing
   **"−1,130 properties left the vacancy list and stayed off it."** Now scoped to ENOUGH (831 of 2,201), and
   **invariant assertions** added so the build *refuses to write output* if a derived count goes negative,
   cycled > gross, ENOUGH > citywide, or the tract counts stop reconciling. That absence is why it shipped.
2. **`durable` was self-referential** — it flagged a closure as "re-noticed" if the property had *any* notice
   starting in the window, including the closure's own opening notice. Rewritten with an ordering test (durable
   iff no notice starts on/after the closure).
3. **Window boundary + units artifact** fully explained the 45-unit residual I had waved off as "snapshot
   effects": 39 intervals end exactly on the baseline (counted as closures though never in baseline stock),
   1 starts exactly on it (counted in stock *and* as new), 39−1=38, plus the 7 overlapping baseline intervals
   = 45 exactly. Boundaries are now strict (`end > baseline`, `start > baseline`).
Also fixed: **`Address` was never in the spells `outFields`**, so `address` was null on all ~18.7k published
points; and stale docstring validation figures (13,233 → the deduplicated 13,226).
- **Dropped the p-value.** ENOUGH tracts are purposively selected (poverty ≥30%), not sampled, so there is no
  null distribution; tracts are also non-independent. Replaced with **indirect standardization**: expected 41.0
  of 45 ENOUGH tracts to fall given citywide band-specific rates, observed 40 → **ratio 0.975**. Corrected for
  starting size, ENOUGH tracts performed *as the rest of the city did, not better*. The page now says so plainly.
- **Tested the "churn" interpretation instead of asserting it** (council's ask): median gap from closure to next
  notice is **5 days**, 89.8% within 30 days, 0.2% beyond a year. Administrative re-issue confirmed.
- **Verified the error class I most suspected was absent:** 7 properties hold overlapping open intervals at
  baseline (13,233 rows vs 13,226 properties) — the pipeline already counts into per-tract sets, so no
  double-count. Documented.

**Done (2026-09-24) — vacancy-reduction layers + citywide tract comparison (Mihir/comms ask).** Two new map
layers: **Vacancy Reductions** (7,199 VBN closures since FY25 as individual points; solid = property stayed
off, hollow = re-noticed — only 2,356 citywide / 833 in ENOUGH are durable) and **Vacancy Change by Tract**
(all 199 Baltimore City tracts, diverging green→red choropleth, ENOUGH tracts outlined). Both canvas-rendered,
off by default. `fetch_vacants.py` now analyses the whole city (199 tracts: 46 ENOUGH + 153 other) rather than
only grantee tracts, so ENOUGH can be compared against a control group.
- **LLM council rejected the obvious headline, and was right.** First draft led on "88.9% of ENOUGH tracts saw
  vacancy fall vs 77.6% elsewhere". Verified against our own data: that measure tracks **starting stock**, not
  performance — tracts with 150+ vacants fell **100%** of the time, tracts with 1–10 fell **62.7%**, and ENOUGH
  holds **0%** of the smallest band vs **40%** of the 150+ band. It is also not significant (z=1.66, p=0.097).
  The median per-tract change is *better* outside ENOUGH (−19.6% vs −14.3%) for the mirror reason. The original
  claim that tract-share was "not distorted by starting size" was **backwards**.
- **Shipped topline instead** (descriptive, gets stronger under scrutiny): 36% of the city's vacant buildings +
  ~40% of its net reduction + 10.9:1 repair-to-demolition + named leaders (Tendea −26.5%, The Y −25.1%).
  The 88.9/77.6 pair is still published, in the body, above a size-bin table that shows why it is confounded.
- Also fixed/disclosed per council: an explicit **non-causal** paragraph (ENOUGH does not fund vacancy work);
  the ranking's 259-building double-count from 3 shared tracts; 483 citywide VBNs (4.2%) falling outside every
  tract polygon; 11 tracts excluded as unable to fall; "these are place measures, not grantee scorecards";
  and a bug where widening the tract universe made the topline read "199 Baltimore tracts" instead of 46.

**Done (2026-09-23) — Analysis #1: gross/net flows + rehab-vs-demolition per grantee.** Extends the vacancy card
with the flow decomposition behind the net change. Since FY25 start, in ENOUGH tracts: **2,211 VBNs closed,
1,793 newly issued, 1,062 rehab permits, 97 City demolitions → 10.9:1 rehab:demolition** (citywide 9.9:1), so
reduction is overwhelmingly *preservation*, not clearance. Per-grantee ratios vary sharply (Park Heights 13.4:1,
Elev8 4.0:1) — worth a look.
- **Important measurement trap found:** **1,378 of the 2,211 closures (62%) were properties re-noticed inside the
  same window** — notice renewal/re-inspection churn, not rehab. Only **~833 properties left vacancy and stayed
  off**. A raw closed-notice count overstates progress ~2.7×. The page leads with 833 and discloses the churn.
- Also documented why gross − new ≠ net: flow columns count *distinct properties*; the stock identity holds on
  *intervals* (citywide 7,199 closed − 5,451 opened = 1,748 ≈ observed −1,703). Both interval counts are published
  in the JSON so the identity is re-checkable.
- `methodology.html` gained a measure-by-measure source/filter table and a **"Reproducing these figures from
  scratch"** section with runnable `curl` spot-checks.

**Done (2026-09-23) — vacancy layers extended to the whole city (Nick's catch).** The map had been drawing only
the vacants *inside* grantee tracts, which makes it impossible to see how ENOUGH's footprint sits against the
city's vacancy pattern — the main reason to map it. Both layers now carry **all** of Baltimore: 11,523 vacant
buildings and 18,676 lots, each flagged `in_enough:1` for the 4,108 / 5,376 inside grantee tracts. Inside points
draw solid and full-size; the rest draw smaller and faded as context. Files renamed
`vacant_*_baltimore.geojson`. Switched to a Leaflet **canvas renderer** — ~30k SVG markers stalled pan/zoom;
canvas renders both layers in ~6s and keeps popups. All counts (stat tile, crosswalk) stay ENOUGH-only; the
out-of-area points are context, not data. Raw payload +5.9 MB (~1.5 MB gzipped over Pages).

**⚠ Open (needs Nick / author) — the Gemini-drafted ENOUGH vacancy explainer does not reconcile.**
[Google Doc](https://docs.google.com/document/d/13sb3wyZVu--2zkFvVyYmbyg8p9RU9Ga0Y6LylRA0UyY/edit) (has comments
from Cleo Hirsch + Madeline Pawlak). Its **tract roster is exactly right** (46 unique, matches ours) but its VBN
counts match no universe in the primary source. Verified against DHCD directly:
- Flagship claim — Urban Strategies / Perkins Somerset Oldtown at **−218 VBNs, 39.1%** — is wrong in sign and
  magnitude. Those 2 tracts (24510280500, 24510030100) hold **57 → 65** VBNs; vacancy **rose 8**. Oldtown as a
  whole neighborhood has only 34 open VBNs, so −218 there is arithmetically impossible.
- Doc totals 8,290 baseline / 7,552 current vs true **4,793 / 4,108**. Doc's total = the exact sum of its rows, so
  it also double-counts the 3 tracts shared by two grantees, and states "44 unique tracts" when its own list has 46.
- Errors run in **both** directions (Urban Strategies 10× high; The Y and Mondawmin *low*), which rules out a
  different-but-valid method. All internal arithmetic is flawless — every % and every baseline−current subtraction
  checks out — which is exactly what makes it convincing. 8,290 would also imply ENOUGH holds 63% of citywide
  vacancy, a failed sanity check against the City's published 13,312.
- Doc's **gross/net framing is good and has been adopted** (it's better than net-only). Its qualitative NAP
  strategy sections stand.
- **Next step:** hand the corrected figures table to the author before the doc goes anywhere. Not overwritten.

**Done (2026-09-23) — Baltimore vacancy inventory + "Vacants Reduction" crosswalk (Mihir's ask).** Mihir
asked to (a) overlay the Power BI dashboard's *Vacants Reduction* section so it can be crosswalked with
ENOUGH, and (b) show total vacants — standing buildings **and** lots — by grantee. Analysed DHCD's
[Vacants Reinvestment Council dashboard](https://app.powerbigov.us/view?r=eyJrIjoiMDM2NDYwMTItYzUyOS00NmYzLWExNmUtYjZlMzc3MWM2ZTAwIiwidCI6IjMxMmNiMTI2LWM2YWUtNGZjMi04MDBkLTMxOGU2NzljZTZjNyJ9)
(9 pages; its Vacants Reduction page filters by neighborhood / priority geography / council / legislative
district — **no ENOUGH dimension**, which is exactly the gap) alongside the Baltimore Fishbowl top-5 piece.
- **Key data finding:** the map's existing BVRI layer is DHCD **Layer 7, the Open Bid List** (~1,200
  properties being marketed) — *not* the vacancy stock. The real universe is open **Vacant Building
  Notices**: 11,523 citywide, plus 18,497 vacant lots. The map had been under-representing vacancy ~10×.
  Sidebar now says "BVRI Open Bid List" to keep the two distinct.
- **Method:** found `Housing/VacantsTimeSlider/MapServer/0`, an **interval** dataset (one row per period a
  property held an open VBN, `DateNotice` → `DateEnd`, with a sentinel end date for still-open). That makes
  the stock computable on *any* date, so there is a genuine baseline and trend rather than two snapshots.
  Validated citywide against DHCD's own dashboard at every FY boundary — within ~0.6% (13,226 vs 13,312 at
  FY25 start; 11,523 vs 11,448 now). Lots from `VacantLot_Test/MapServer/0` (snapshot only, no history).
- **Results:** ENOUGH's 46 Baltimore tracts hold **4,108 vacant buildings + 5,362 lots = 9,470 total** —
  **36% of the city's vacant buildings**, 32% of all vacants. Buildings fell **−685 (−14.3%)** since FY25
  start vs citywide −1,703 (−12.9%), so ENOUGH communities account for ~**40% of the entire citywide
  reduction**. Also reproduces the Fishbowl neighborhood table from source data (Harlem Park exact at
  501→439).
- **Shipped:** `scripts/fetch_vacants.py`; two map layers (vacant buildings near-black, vacant lots grey,
  both off by default, in `pointPane`); a 7th stat tile "Total Vacants in Grantee Tracts" that recomputes
  per grantee; and a **"Vacant housing in ENOUGH communities"** card on the crosswalk mirroring the
  dashboard's Net-VBN-Change table by grantee, with a neighborhood view behind a toggle, plus
  methodology Layer 9.
- **Caught a double-count before shipping:** all 3 shared Baltimore tracts are served by two grantees, so
  summing per-grantee rows overstated the ENOUGH baseline (5,054 vs true 4,793). `enough_totals` now carries
  a de-duplicated baseline/change and the page uses it; the table notes why rows exceed the total.

**Done (2026-09-23) — Baltimore-City-only layers now use a Baltimore City denominator (Nick's catch).**
The crosswalk was scoring **BVRI** and the **DHCD Impact Areas** against the statewide roster (28
communities / 111 tracts), which is misleading: those are Baltimore City programs, so a grantee tract in
Frederick or Salisbury *cannot* overlap them, and counting it as a miss reports a jurisdiction boundary as
a program gap. `build_crosswalk.py` now derives the Baltimore City grantee footprint from
`JURSCODE == 'BACI'` — **46 tracts across 11 organizations**, all of which serve only city tracts — and
`summarize()` takes an optional `universe` that rescopes `total_tracts` / `total_communities` and each
grantee's in-universe tract count. Exposed as `totals.baltimore_city` plus a per-layer `universe` object
(which also carries `statewide_tracts`/`statewide_communities`, so nothing is hidden). Restated:
**BVRI 10/11 communities + 33/46 tracts** (was 10/28 + 33/111) and **DHCD 6/11 + 21/46** (was 6/28 + 21/111)
— i.e. the correction is substantially *in the programs' favour*. The crosswalk cards now say "Baltimore
City ENOUGH communities" in the headline and bar labels, carry an amber "why the denominator is smaller
here" note, and list the 11 communities behind a disclosure toggle; the page explainer gained an "Out of
what?" definition, and `methodology.html` a "What each layer is scored out of" section. Statewide layers
are untouched. **Also corrected a stale figure:** `CLAUDE.md` said 40 Baltimore City grantee tracts; it is 46.

**Done (2026-09-23) — basemap moved off CARTO.** CARTO put its hosted basemaps behind an API key and
started rendering an "API KEY REQUIRED / carto.com/basemaps/apikey" watermark diagonally across the
tile PNGs, so the map had a visible watermark on every tile. The watermark is raster pixel data, so no
CSS/styling change could hide it — the tiles had to come from elsewhere. Replaced with **Esri Light Gray
Canvas** (`server.arcgisonline.com/.../Canvas/World_Light_Gray_Base` + `World_Light_Gray_Reference`),
added as the two layers Esri publishes it in, both kept in Leaflet's default `tilePane` so place labels
stay *under* the data (matching Positron's old behavior). No API key needed. Chose this over registering
a CARTO key because the repo is public and a basemap key must ship client-side, where it's exposed by
definition; Esri is also the same platform serving most layers here (iMap), and Light Gray Canvas is a
close visual match for Positron. Attribution updated; `methodology.html` Basemap section rewritten with
a dated change note. Verified in a headless browser: 48 tiles load, no failed requests, no console
errors, labels render, and the pane z-order still puts grantee tracts and BVRI points above the fills.

**Done**
- Initial build: BVRI × ENOUGH overlay map for Baltimore City (`8d68452`).
- Simplified to a grantee-only tract layer + fixed a blank-map render bug (`d3687bb`).
- Grantee tracts grouped by organization with distinct per-grantee colors (`1862bbb`).
- Added **NMTC eligibility** layer from CDFI Fund (`07ed842`).
- Added a **methodology page** (`docs/methodology.html`) documenting all four data sources (`c562a3b`).
- Expanded from Baltimore-only to a **statewide** default view with a "Zoom to Baltimore City" button (`c997448`).
- Added Opportunity Zones layer; switched from **eligible (OZ 2.0)** to **designated (2018 TCJA)** zones
  from iMap `MD_IncentiveZones` Layer 14 — 149 tracts, no rural split (`8aff097` + follow-up).
- Added **Maryland Enterprise Zones** layer (MD Commerce via iMap `MD_IncentiveZones`): 32 zones +
  2 Focus Areas (folded into one geojson with a `focus_area` flag), off by default, orange fill.
  Added a 5th stat-bar metric "Grantee Tracts in Enterprise Zones" (86 statewide). Originally computed
  client-side via a polygon-vs-polygon vertex-containment helper; **as of 2026-07-21 this now reads the
  server-side `crosswalk.json` value** (see below) and the client-side helper was removed. Requested via
  the state EZ lookup app.
- All map layers wired in `docs/index.html`: grantee tracts (colored by org, on by default),
  BVRI vacants (red points), DHCD Impact Investment Areas (off), NMTC (two distress tiers, off),
  Opportunity Zones (designated, off), OZ 2.0-eligible tracts (purple, off), Enterprise Zones (off),
  Just Communities (magenta, off).
- **Just Communities layer added (2026-08-24, per Mihir's 8/20 "Another data layer" email).** He linked DHCD's
  ArcGIS "Just Communities Viewer"; note "JUST" was the *program name*, not the adverb "only". Shipped the **419
  designated Just Communities** tracts from the authoritative iMap `MD_HousingDesignatedAreas` **Layer 9** (GEOID
  set verified identical to the app's own layer, so the state service is used for better provenance + a county
  field). Created by the **Just Communities Act of 2024** (HB 241/SB 308). Exact-GEOID join (2020 tracts, like
  NMTC/OZ2): **81/111 grantee tracts, 26/28 communities**. New 6th stat-bar metric "Grantee Tracts in Just
  Communities" (per-grantee aware), popup of the designation indicators, crosswalk card, methodology Layer 8,
  `scripts/fetch_jc.py`. Coordinates rounded to 5dp in the fetch script (6 MB → 3.4 MB).
- **Map pane z-order bug fixed (found while adding the above).** Context layers had been rendering *on top of*
  the grantee tracts, because Leaflet stacks by the order layers get toggled on. Introduced explicit panes
  (`ctxPane` 410 → `granteePane` 450 → `pointPane` 460), so designation polygons always sit under the grantee
  tracts and the BVRI points sit on top. Most visible with Just Communities, which blankets Baltimore City
  (167 tracts there) — its fill is also deliberately lighter (0.22) than the other designation layers.
- **LLM-council review done + acted on (2026-08-24).** All 5 advisors ran; 3 independent peer reviewers
  unanimously ranked the Contrarian strongest and the Expansionist's suggestions the biggest blind spot. Fixed:
  (a) **the real bug — `redlining` is only ever `true`(184)/`null`(235), never `false`.** The page had said "43
  have a documented history of redlining", implying the other 38 were not redlined; HOLC only mapped a few MD
  cities, so `null` means "no map exists". Reworded on the crosswalk + methodology and in the popup ("No HOLC
  map for this area"), and the schema row now states the field is never `false`. (b) narrowed an over-claim
  ("no State funding-priority designation reaches them" → "none is a designated Just Community", + a note that
  only mapped programs are covered). (c) disclosed the **30 non-designated grantee tracts** by county
  (PG 10, AA 7) incl. the 2 communities with zero, and offered PFA-clipping as the likely (unverified) mechanism.
  (d) added a **v1.0 caveat box** (4 of 14 criteria unsourced, ≥13.5 is administrative not statutory, a v2.0 will
  move the counts) + a Vintage/fetch-date stamp. (e) Outsider fixes: quoted the designation name so it doesn't
  read as a value judgment, named the three stacked programs explicitly, units + direction on every popup row,
  reversed the ambiguous "19% of them" phrasing. Declined (per peer review): on-by-default, naming the 6
  "invisible" tracts on a public page, and sending the redlining count onward as an analytic covariate.
- **OZ 2.0-eligible layer added (2026-08-03, per Mihir).** Sourced the two datasets from
  https://opportunityzones.com/location/maryland/ : (1) **451 OZ 2.0-eligible tracts** (2020–2024 ACS,
  each with MFI-vs-area ratio + poverty rate) — a new statewide layer, purple, off by default; and
  (2) a **rural/non-rural flag** on the existing 149 designated OZs (47 rural), rendered as a dashed
  yellow outline. Eligible-tract GEOIDs (2020 vintage) join exact-match to grantee tracts: **92/111
  grantee tracts across 26/28 communities are OZ 2.0-eligible** — i.e. positioned to keep a federal
  capital-gains incentive after the 2018 zones lapse in 2028. Built by `scripts/fetch_oz2.py`
  (parses the page tables, joins geometry from `enough-eligibility-analysis/.../tracts_2026.geojson`,
  rewrites the designated-OZ geojson with the rural flag). Added to `build_crosswalk.py` (exact-GEOID
  join, `oz2` layer key), the map, the crosswalk page (new card + nomination-cap context line), and
  `methodology.html` (new Layer 6; EZ renumbered to Layer 7). Verified in a headless browser (no
  console errors, both layers render, crosswalk card in place). Kept out of the statewide "stacking/gap"
  histogram since it's forward-looking eligibility, not a current designation.
- BVRI-in-grantee-tracts overlap (565 as of the latest data) computed client-side via
  point-in-polygon ray casting; recomputes per-grantee when one is selected in the sidebar.
- **ENOUGH Crosswalk page (`docs/crosswalk.html`)** — for each non-grantee layer, shows how many
  ENOUGH communities + grantee tracts overlap, per-community breakdown, NMTC distress tiers, a
  plain-language explainer, a hero takeaway ("all 28 communities in ≥1 program"), a "why it matters"
  line per layer, and a **stacking/gap section** (how many statewide programs coincide per tract; which
  tracts sit in zero — 6 tracts, Boys & Girls Clubs of Harford/Cecil + One Annapolis). Data-driven from
  `crosswalk.json`. Built + reviewed by the LLM council, then iterated (see below). Linked from the map
  header and the methodology nav.
- **EZ stat moved to server-side crosswalk (headline 86, footnote 71).** The map's "Grantee Tracts in
  Enterprise Zones" headline previously used a loose client-side vertex-containment test (86). It now
  reads the value from `crosswalk.json`, so the map, its per-grantee sidebar count, and the crosswalk
  page all agree; the old client-side polygon helpers were removed from `index.html`. Per Nick's call,
  the EZ headline uses **any-overlap** (a tract touching a zone = 86), with the stricter **≥5%-area**
  count (71) footnoted on the crosswalk page and documented in `methodology.html`. The 15-tract gap is
  boundary slivers (all <5% of tract area, smallest 0.5%). OZ/DHCD still use ≥5% (OZ's threshold is
  validated against its exact-GEOID join; EZ has no tract-based ground truth, so any-overlap is used).
- **LLM council review done + acted on.** 5-advisor council flagged: a real double-count in the BVRI
  per-grantee breakdown (shared tracts — now footnoted, not hidden), "any-one-tract overlaps" inflating
  coverage (now tract-share shown alongside community-share everywhere), jargon (added plain-language
  explainer + per-layer "why it matters"), the 86→71 restatement needing a visible note (added),
  low-contrast text (darkened `#a0aec0` → `#5a6678`), and reproducibility gaps (see Workstream B).
  Also surfaced the highest-value framing: lead with "every ENOUGH community is validated by other
  distress definitions" + the gap view — both now on the page.

**Open (build — can be done in-repo)**
- [ ] **Lazy-load the off-by-default layers.** `index.html` fetches every geojson up front in one `Promise.all`
  (~25 MB: NMTC 9.4 MB, EZ 8.4 MB, JC 3.4 MB, OZ 1.9 MB, OZ2 1.0 MB), including layers that are off by default.
  Load each on first toggle instead. Highest-value follow-up in the repo; flagged by the council as pre-existing
  debt rather than a blocker. Rounding coords to 5dp (as `fetch_jc.py` does) would also shrink the older layers.
- [ ] Consider a v2.0 watch on Just Communities — DHCD said it intends to add the 4 unsourced criteria; re-run
  `fetch_jc.py` and rebuild the crosswalk when that lands.
- [ ] Decide whether to ship the additional DHCD layers (vacant building notices, demolitions,
  receivership — Layers 0/1/2/4/5 of the same feature server) noted as available in methodology, or
  keep the map to just the open-bid Vacants to Value list.
- [ ] Optional: a standing DQ/freshness note on the map for the layers with differing ACS vintages
  (ENOUGH = 2024 ACS; NMTC = 2016–2020 ACS) — currently only documented in `methodology.html`.

## Workstream B — Data fetch scripts

**Done**
- `scripts/fetch_bvri.py` (70 lines) — pulls Layer 7 (Vacants to Value, 1,192 properties) and Layer 10
  (7 Impact Investment Areas) from Baltimore City DHCD ArcGIS into `docs/data/`.
- `scripts/fetch_nmtc.py` (145 lines) — pulls the CDFI Fund NMTC service and **recomputes the distress
  tier** locally (the source service has no single tier field): 587 eligible tracts statewide
  (350 Severe Distress, 237 Distressed).
- `scripts/fetch_oz.py` — pulls MD iMap `MD_IncentiveZones` Layer 14 (designated Opportunity Zones):
  149 tracts statewide (2018 TCJA designation, in effect through 2028). Rural/non-rural split now
  added by `fetch_oz2.py` (below), not this script.
- `scripts/fetch_oz2.py` — parses https://opportunityzones.com/location/maryland/ for the 451
  OZ 2.0-eligible tracts (MFI ratio + poverty) and the rural flag on the 149 designated OZs. Joins
  eligible-tract geometry by GEOID from `enough-eligibility-analysis/.../tracts_2026.geojson`
  (451/451 matched); writes `oz2_eligible_maryland.geojson` and rewrites `oz_designated_maryland.geojson`
  with a `rural` bool. Source is a scraped HTML table — re-verify table structure if the page is redesigned.
- `scripts/fetch_ez.py` — pulls iMap `MD_IncentiveZones` Layer 4 (Enterprise Zones, 32) + Layer 5
  (Focus Areas, 2) into `ez_maryland.geojson` with a `focus_area` flag. Note: Layer 5 lacks the
  `extent`/`Expiration` fields, so the script requests `outFields=*` rather than a fixed field list.
- `scripts/build_crosswalk.py` (Shapely) — computes ENOUGH × every layer overlap → `docs/data/crosswalk.json`.
  Join per layer: NMTC exact-GEOID; OZ/EZ/DHCD geometric ≥5% tract-area; BVRI point-in-polygon. Also
  computes the statewide stacking histogram + zero-program gap list. Stamps a `source_hash`; `--check`
  mode exits 1 if the committed JSON is stale vs. source geojson. Needs shapely (PEP 668 blocks system
  pip) — pinned in `scripts/requirements-crosswalk.txt`; run from a repo-local `.venv-geo`.

**Open (build — can be done in-repo)**
- [ ] **No saved grantee-tract build script.** The `grantee_tracts.geojson` build is only an inline
  Python snippet in `CLAUDE.md`. Worth saving as `scripts/build_grantee_tracts.py` so the rebuild is
  reproducible like the other three fetchers.
- [ ] **Reconcile the grantee-tract build source.** `CLAUDE.md`'s prose and `methodology.html` say the
  tracts are built from `enough-eligibility-changes` (`tracts_2026.geojson` + `map_filters.json`), but
  the inline snippet reads `../enough-eligibility-analysis/docs/data/tracts_2026.geojson` and joins on
  `grantee_geoids.json` (no `grantee_name` join shown). Confirm the canonical source repo/filename and
  which path actually produced the committed `grantee_tracts.geojson` before relying on the snippet.
- [ ] `fetch_nmtc.py`'s header docstring still says it writes `nmtc_baltimore.geojson`; the code writes
  `nmtc_maryland.geojson`. Cosmetic, but worth fixing to avoid confusion.

## Workstream C — Data freshness

**Done**
- All data committed under `docs/data/` (geojson + json) so the site is self-contained and offline-buildable.

**Open (operational — Nick)**
- [ ] BVRI is a **live, daily-refreshed** DHCD dataset; the committed `bvri_vacants.geojson` is a snapshot
  from the 2026-05-28 build. Re-run `python3 scripts/fetch_bvri.py` and commit before any external share
  if currency matters.
- [ ] Designated OZ layer (2018 TCJA) is stable through 2028. A future OZ 2.0 designation cycle will
  replace it — re-pull `fetch_oz.py` when MD publishes the new designated list.

## Cross-cutting decisions still open
1. **Scope creep vs. simplicity** — the original ask (Mihir) was deliberately minimal (one grantee
   layer, one BVRI layer). It has since grown to **six** map layers (grantee, BVRI, DHCD areas, NMTC,
   Opportunity Zones, Enterprise Zones) + statewide view + a methodology page + a full **ENOUGH Crosswalk
   page** + overlap stats. Confirm with Mihir that the expanded version is what he wants, or keep a
   trimmed "as-requested" view. **Mihir has not yet seen the crosswalk page** — surface it to him.
2. Whether to add the other DHCD vacant-property datasets (see Workstream A) — depends on the use case.

## Repo hygiene
- Git on `main`, clean working tree. Latest commit `0b7ea67` (2026-07-21) — "Add ENOUGH Crosswalk page
  + server-side overlap crosswalk" — pushed to `origin/main`; GitHub Pages auto-deployed.
- **New this session:** `docs/crosswalk.html`, `docs/data/crosswalk.json`, `scripts/build_crosswalk.py`,
  `scripts/requirements-crosswalk.txt`; edits to `index.html`, `methodology.html`, `CLAUDE.md`, `STATUS.md`.
- To resume the crosswalk build: `python3 -m venv .venv-geo && .venv-geo/bin/pip install -r
  scripts/requirements-crosswalk.txt`, then `.venv-geo/bin/python scripts/build_crosswalk.py [--check]`.
  (This session used a throwaway `/tmp/geoenv` venv — a repo-local `.venv-geo` is the durable path.)
- **Pushed to a PRIVATE GitHub repo:** `Maryland-Governors-Office-for-Children/enough-bvri-map`
  (remote `origin` set). Deployed via **GitHub Pages from `docs/`**.
- **No `.gitignore`** — all data files (`docs/data/*.geojson`, `*.json`) are intentionally committed,
  since every layer is built from public, non-sensitive sources (no PII; ENOUGH tract roster is public).
  If a `.claude/settings.local.json` is ever added, gitignore it.
