# ENOUGH × BVRI Map — Status & Open Steps

_Last reviewed: 2026-07-21 (ENOUGH Crosswalk page + LLM-council iteration + EZ headline set to any-overlap; pushed)._ Living index of what's done, what's open, and what needs a decision.
See `CLAUDE.md` for project context; `docs/methodology.html` for the per-layer data-source documentation.

A GitHub-Pages site (`docs/`) with three pages: a Leaflet **map** showing where active ENOUGH grantee
tracts overlap Baltimore Vacants Reinvestment Initiative (BVRI) activity plus federal/state incentive
layers; an **ENOUGH Crosswalk** page breaking down that overlap program-by-program; and a
**methodology** page. Originally requested by Mihir Parikh; intentionally simple, since expanded.
**Live:** https://maryland-governors-office-for-children.github.io/enough-bvri-map/

## Workstream A — Map build & layers

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
  Opportunity Zones (designated, off), Enterprise Zones (zones + focus areas, off).
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
  149 tracts statewide (2018 TCJA designation, in effect through 2028). No rural/non-rural split.
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
