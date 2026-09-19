# data_web_browser: design and file guide

## What this is

A searchable web browser over the ALS pipeline's raw/processed dataset
collection (`/lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS`), plus
the S3 publish pipeline that feeds it. Built 2026-09-05.

**Deliberately standalone.** This project has no connection to, dependency
on, or data pulled from `neurodegen-commons` (its `registry.yaml`,
gene-signature/DE data, or its site). Everything here is sourced only from
EXTERNAL_DATASETS' own native files (`studies.tsv`, `all_samples.tsv`,
per-study `README.md`, and the coordination dir's `*_status.json` files).
If a field is missing that you want in the browser, add it to the
collection's own metadata — don't import it from elsewhere.

**The MCP server is intentionally not built yet.** The user wants a
broader discussion on it before it's designed. This project currently
covers: the web browser, and the S3 publish/metadata pipeline with a live
auto-update mechanism.

## Architecture in one paragraph

The metadata catalog (`catalog.json`/`samples.json`) lives in S3, not
baked into the web app's build. The frontend fetches it directly at
runtime on every page load (`cache: 'no-store'` + a cache-busting query
param), so there's nothing to rebuild or redeploy when new data lands —
only the JSON in S3 changes. The `publish.py` pipeline is what changes it:
sync new/updated studies' processed files to S3, rebuild the catalog
(folding in what's actually now in the bucket), push the refreshed JSON,
and issue a CloudFront invalidation so the change is visible within
seconds. See "Update flow" below for the exact sequence.

## Directory layout and what each file does

```
data_web_browser/
  DESIGN.md          <- this file
  README.md          <- quickstart: run the pipeline, build/run the web app
  pipeline/           Python, reads EXTERNAL_DATASETS + writes to S3
  web/                React (Vite) SPA, fetches metadata from S3/CloudFront at runtime
  mcp_server/         Remote MCP server (search/detail/download tools) -- see its own README.md
  infra/              Terraform for the S3 bucket + CloudFront + IAM + MCP Lambda (NOT applied yet)
```

### `pipeline/`

| File | Purpose |
|---|---|
| `catalog_schema.py` | The single typed definition of every record shape (`StudyRecord`, `SampleRecord`, `ProcessedFile`, `RolePhase`, `Catalog`). Every other file traces back to these field names — don't invent a parallel shape elsewhere. |
| `sources.py` | All reads of EXTERNAL_DATASETS' native files: `studies.tsv` (including its `summary` column), `all_samples.tsv`, per-study `README.md` (its `## Abstract`, `## Summary`, and, as a fallback, a header parser — see "studies.tsv lags behind studies/" below), `build_summary.json`, and the coordination dir's `*_status.json` files. Also owns the field-level cleanup helpers (`normalize_organism`, `dedupe_joined`, `build_case_insensitive_canon`, paren-aware `split_multi`) — see "Disease status / tissue filters" below. Nothing here writes anything. |
| `build_catalog.py` | Assembles `catalog.json` + `samples.json` from `sources.py`'s readers. Optionally takes `--bucket` to fold in the *live* S3 state (so `available_externally` is ground-truth, not a guess) — without it, runs entirely read-only against HTCF with no AWS credentials needed. |
| `s3_sync.py` | Decides which studies are eligible to publish (see "Eligibility and access safety" below) and uploads their `processed/` data files to S3, idempotently (sha256 stored as S3 object metadata, unchanged files skipped). Writes a skip log explaining every excluded study. |
| `publish.py` | The one script an actual "upload new data" run needs: composes `s3_sync` → `build_catalog` (with the resulting S3 state) → upload metadata to S3 → CloudFront invalidation → record the run in the coordination dir. `s3_sync.py`/`build_catalog.py` can be run standalone for testing; `publish.py` is what a real automated run should call. |
| `coordination.py` | Thin helpers for participating in the existing multi-session coordination protocol (`CHANGELOG.jsonl` append, this pipeline's own `s3_publish_status.json`) — see "Coordination" below. |
| `conftest.py` | Lets `pytest` run from inside `pipeline/` resolve `import pipeline.<module>` for the small number of tests that import it that way. |
| `tests/` | pytest suite, one file per module above. Run with `pytest tests/` from inside `pipeline/`. |

### `web/`

A Vite + React SPA, no server runtime, no build-time data embedding.

| File | Purpose |
|---|---|
| `src/api.js` | Fetches `catalog.json`/`samples.json` from `VITE_METADATA_BASE_URL` (defaults to `/data` for local dev) at runtime — this is the whole "updates right away" mechanism; see Architecture above. |
| `src/facets.js` | Derives every filter's option list from whatever distinct values are actually present in the fetched catalog — no hardcoded taxonomy, so new studies with new values never get silently excluded from the filter UI. Facets: organism, assay type, disease status, tissue, primary route, journal. |
| `src/format.js` | `formatLabel`/`distinctFormats` — human-readable processed-data format (h5ad/parquet/tsv/...) derived from a file's extension. Purely presentational; not the pipeline's own data/doc/metadata classification. |
| `src/App.jsx` | Top-level state: fetch on mount, hold filters/query/selection, wire the components together. |
| `src/components/FilterSidebar.jsx` | Collapsible checkbox facet groups (collapsed by default, click a header to expand — a badge shows the active-selection count when collapsed), free-text search box, and a "Clear filters" button (resets checkbox facets only, not the search box). |
| `src/components/StudyTable.jsx` | The main filtered/sorted study list, including a "Data format" column (or "not yet processed"). |
| `src/components/StudyDetail.jsx` | Per-study modal: title/journal/DOI, format badges, plain-language summary, accessions, notes, a processed-data-files table (name/format/size, data-category files only), and a sample table (capped at 200 rows client-side — see Honest limitations). |
| `src/styles.css` | Plain CSS, no framework. |

### `mcp_server/`

**Deprecated as of 2026-09-14 — see "MCP server deprecated" below.** Kept
for reference; not under active development.

The remote MCP server — see its own `README.md` for local dev/deploy
instructions and the "MCP server (2026-09-09)" section above for the full
design. Briefly: `server.py` wires up 7 tools (`tools/*.py`) and 5 curated
reference resources (`resources/*.md`); `catalog_cache.py`/`s3_clients.py`
handle S3 access (ETag-gated caching, the two-boto3-identity split for
presigning); `resource_links.py` attaches MCP `resource_link` content
blocks to tool results; `tool_response.py`'s `build_result()` is what every
tool uses to return its result -- it puts the full data directly in the
text content block (not only in `structured_content`, which not every MCP
client forwards to the model -- see "MCP server" below for why this
matters); `fixtures/` holds a trimmed real slice of the HTCF collection for
local testing without any AWS credentials.

### `infra/`

Terraform for one S3 bucket (data + metadata + the built web app, at
different prefixes), one CloudFront distribution in front of it (Origin
Access Control — the bucket itself is never public), one IAM policy for
whichever principal runs `publish.py` (`main.tf`), and the MCP server's
Lambda + Function URL + two IAM identities (`mcp.tf`, additive). Validated
with `terraform validate` but **not applied** — see "Not yet done" below.

## Update flow (the auto-update mechanism)

1. `s3_sync.py` finds newly-eligible studies and uploads their `processed/`
   "data"-category files (h5ad, h5mu, parquet+tsv — not doc/metadata
   sidecars like `conversion_log.md`, and never raw FASTQ/BAMs) to
   `s3://<bucket>/processed/<study_id>/`.
2. `build_catalog.py` rebuilds the catalog from EXTERNAL_DATASETS' native
   sources plus a live listing of what's now actually in the bucket.
3. `publish.py` uploads the refreshed `catalog.json`/`samples.json`/
   `last_updated.json` to `s3://<bucket>/metadata/` and issues a CloudFront
   invalidation for `/metadata/*` and any changed `/processed/<id>/*`
   paths.
4. The web app has no build-time data dependency — it fetches the JSON
   fresh on every load. Once step 3's invalidation lands (seconds), new
   data is visible with no redeploy.
5. `publish.py` registers as a new `s3_publish` role in the existing HTCF
   coordination system (see next section).

## Eligibility and access safety

A study is only synced if **all** hold:
1. It's not one of `build_summary.json`'s deliberately-excluded entries
   (keyed on the entry's `status` text starting with `"SKIPPED"` — e.g. the
   one dbGaP-controlled study, `phs002864`/`HNSCC_Pembrolizumab_dbGaP`).
   **Not** keyed on `study_dir` being null — see the pitfall below.
2. Its conversion phase (per `conversion_status.json`) is `converted` or
   `converted_partial`.
3. `studies/<id>/processed/` actually contains at least one "data"-category
   file.

**A real pitfall found and fixed while building this (2026-09-05):** the
obvious signal for "deliberately excluded," `build_summary.json`'s
`study_dir` field being `null`, is not actually reliable — `SRP566214_dataset`
has `study_dir: null` too, but its `status` field says "COMPLETE," not
"SKIPPED." Using `study_dir is None` as the skip signal would have
silently excluded a real, legitimate study. Fixed to key on the `status`
text instead (see `sources.skipped_study_ids`).

## Coordination

This pipeline participates in the existing multi-session protocol at
`/lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination` (full spec in
that dir's `PROTOCOL.md`) as a new role, `s3_publish`:
- Appends to the shared, append-only `CHANGELOG.jsonl` after every
  `publish.py` run (dry runs too, tagged `dry_run_published`, so the audit
  trail shows what was previewed vs. actually done).
- Owns and writes its own `s3_publish_status.json`, following the same
  `{phase, note}`-per-study shape every other role's status file uses. A
  **real** run's status update also corrects any study that flipped from
  eligible to skipped since the last run (e.g. re-verification demoted its
  conversion phase) — a dry run never touches this file at all, since
  nothing it "did" actually happened.

**Not done, deliberately:** adding `s3_publish` to `PROTOCOL.md`'s role
table itself. That file's own ownership rule says it's edited only at
explicit user request — worth doing, but the user should say so first.

## Another real discovery: CELLxGENE's organism field needs normalizing

Found by actually driving the built web app in a browser against real data
(2026-09-05), not by reading code: the "Organism" filter showed one entry
as raw stringified JSON, `[{'label': 'Homo sapiens', 'ontology_term_id':
'NCBITaxon:9606'}]`, instead of "Homo sapiens". Traced to `all_samples.tsv`:
the two CELLxGENE-sourced studies (`Brain2025_Multiome`,
`CrypticExon_ActaNeuropathol2023`) have their `organism` cell holding
CELLxGENE's raw ontology-mapped API response, Python-repr'd into the TSV,
rather than a plain string like every GEO-sourced study has.
`sources.normalize_organism()` detects this exact shape (safely, via
`ast.literal_eval`, never `eval`) and extracts just the label(s); applied
in `build_catalog.py` wherever an `organism` value is read. This is a
one-way display fix in this project only — `all_samples.tsv` itself (owned
by `download_metadata`) was not touched.

## Disease status / tissue filters, and a paren-splitting bug (2026-09-06/07)

Added two new study-level facets, `disease_statuses` and `tissues`,
aggregated from `all_samples.tsv`'s `disease_status`/`tissue_or_cell_type`
sample fields the same way `organisms` already was. Both fields turned out
messier than organism ever was:

- **`disease_status`** (50 raw distinct values): real duplication by
  letter case alone -- `Control`/`control` (112 rows each), and an actual
  typo, `Other Neurological Disorders` vs `Other Neurological DIsorders`,
  which happens to be a pure case variant of the correct spelling.
- **`tissue_or_cell_type`** (86 raw distinct values): many cells are a
  value repeated with itself, e.g. `Cerebellum; Cerebellum`.

Fixed generically, not with a hardcoded taxonomy:
- `sources.build_case_insensitive_canon()` merges values that differ only
  by case, canonicalizing to whichever casing is most frequent (ties break
  alphabetically). Values that differ by more than case (`Control` vs
  `CTL`) are deliberately left distinct -- this isn't a semantic merge.
- `sources.dedupe_joined()` collapses a `;`-joined cell down to its
  distinct parts (`"Cerebellum; Cerebellum"` → `"Cerebellum"`), leaving
  genuinely different parts (`"skin; iN"`) untouched.
- Both are applied in `build_catalog.py`'s `build()` (study-level
  aggregation) and `build_sample_records()` (sample-level records) --
  built once per call from the *entire* sample corpus so a value
  canonicalizes the same way regardless of which study it's aggregated
  from.

**A second, unrelated bug found by the user while reviewing assay-type
values**: `sources.split_multi()` (used for `studies.tsv`'s `assay_types`
and `gse` columns) split on every `,`/`;` unconditionally. Two real
`assay_types` values have a comma *inside* parentheses --
`"scRNA-seq (iPSC-MN, ddSEQ + 10x)"` (Ho2021_CellSystems) and `"scRNA-seq
(Smart-seq2, iPSC-MN)"` (Schweingruber2025_NatComms) -- so the naive split
broke each into two fragments, one ending in an orphaned `(` and the other
starting with an orphaned `)`. Fixed by making `split_multi` track
paren-depth and only split at depth 0. Verified against the real
collection post-fix: both values now come through as one intact string.

## Making the UI legible to people unfamiliar with the pipeline (2026-09-07)

The user's core framing for this pass: **people using this tool won't know
how the pipeline was built or what its internal vocabulary means.**
Several fields that make perfect sense to someone who ran the conversion
jobs are meaningless (or actively confusing) to an outside researcher.
Removed or replaced, in order:

- **Status column / Conversion status filter** — removed entirely (table
  column, sidebar facet, and the `conversion_phase` field in
  `facets.js`/`FilterSidebar.jsx`). Values like `converted_partial` /
  `blocked` / `out_of_scope` are pipeline-internal vocabulary with no
  meaning to an external user.
- **"Available externally" column/filter** — removed (table column and
  sidebar facet). It's also just non-functional right now (no S3 bucket
  exists yet), which made it doubly not worth keeping visible. The
  underlying `available_externally` field stays in the data model for when
  an MCP server/S3 bucket actually exists.
- **"Pipeline status" section in the detail modal** — removed entirely
  (the Download/Conversion/Verification/Alignment rows with raw internal
  notes -- Slurm job IDs, "DecontX re-run", "scratch→lts copy", references
  to `conversion_process.md`). This was the same problem as the Status
  column, just with far more internal detail exposed.
- **Paper Abstract → plain-language Summary**: replaced `study.abstract`
  (wildly inconsistent in length/presence across studies, and assumes
  domain background) with `study.summary`, sourced from `studies.tsv`'s
  own `summary` column (added by the download_metadata role, 2026-09-06/07
  — a consistent 3-5 sentence plain-language summary for all 41 studies)
  falling back to the README's `## Summary` section
  (`sources.load_readme_summary`) only if a study isn't in studies.tsv at
  all. **Checked before writing any new summarization code** — this data
  already existed, no need to generate it ourselves.
- **New: a clear processed-format indicator.** Added `web/src/format.js`
  (`formatLabel`/`distinctFormats`), deriving a human label (`h5ad`,
  `parquet`, `tsv`, ...) from each processed file's extension — this is
  presentational only, distinct from `sources.classify_file`'s
  data/doc/metadata pipeline classification. Surfaced in two places: a
  "Data format" column in the main study table (or "not yet processed" in
  italic grey when a study has no processed files yet), and a row of
  badge pills at the top of the detail modal. This directly answers what
  the tool mainly serves people: **already-processed data (h5ad, parquet,
  etc.), not raw FASTQ** — raw sequencing files are never listed here at
  all (only `processed/` is scanned, never `raw/`), so an empty format
  list correctly reads as "nothing processed yet," not "no data at all."
- **Files table**: renamed "Processed data files," filtered to
  `category == "data"` only (hiding doc/metadata sidecars like
  `conversion_log.md` — not useful to show), and its "Category" column
  replaced with "Format" (the same `formatLabel` mapping).

**A "Clear filters" button** was also added next to the result count
(`FilterSidebar.jsx`) — resets all checkbox facet selections in one click,
disabled when none are active, showing a live count when they are. It
deliberately does not clear the free-text search box, which is a separate
control.

**Filter semantics, confirmed for the user**: within one facet group
(e.g. two Disease status checkboxes), matching is OR — a study shows if it
has *any* selected value. Across different facet groups, it's AND. This
is `facets.js`'s `matchesArrayFacet` using `.some()`; standard
faceted-search behavior, not a bug.

## Visual design pass (2026-09-07, via the `frontend-design` skill)

The user explicitly did not want a "generic Claude" look. Presented 4
distinct visual directions grounded in the actual subject (lab notebook /
instrument console / specimen catalog / clinical report); user picked
**specimen catalog** — modeled on natural-history specimen records:
each study is a record with a catalog number (accession), collected
material (summary), and condition (processed format).

Tokens: `Piazzolla` (serif, titles) + `Libre Franklin` (UI/body) +
`IBM Plex Mono` (identifiers only — accessions, DOIs, filenames). Cool
stone background (`#eeeee7`, deliberately not the cliché warm cream),
sage green as the one accent, ochre reserved for an actual state
("not yet processed" badges/notes), never decorative. Hairline borders
throughout, no shadows, no uniform card-radius.

**Two real mistakes caught only by screenshotting and looking, not by
writing the CSS**:
- Styled every `<h3>` in the detail modal (`.study-detail h3`) as
  tracked-out uppercase mono — realized on review this is *exactly* the
  "tracked-out ALL-CAPS eyebrow label above every heading" tell the skill
  itself lists as a top AI-design giveaway. The specimen-label metaphor
  only justifies that treatment on one specific, deliberate element (the
  catalog-number tag); applying it to every section heading was the
  generic default creeping back in. Fixed to sentence case.
- Adding a prominent "catalog number" tag (the study's primary accession)
  duplicated that same accession in the `study-accessions` line below it
  for any single-GSE study. Fixed in `StudyDetail.jsx` by excluding
  whichever accession is already shown as the catalog number from the
  accessions list.

**Known open item, deliberately not fixed yet in this pass** (flagged to
the user, response pending): the `study-notes` box still surfaces
`studies.tsv`'s raw `notes` column verbatim, which mixes genuinely useful
scientific caveats (e.g. "GEO's characteristics field mislabels 6
samples...") with pure pipeline-process commentary (e.g. "Backfilled
2026-09-06 from studies/.../README.md header (row was missing from
studies.tsv...)") that means nothing to an outside researcher — the same
category of problem as the Status column removed earlier. Needs a
decision on how to separate the two before touching it.

## A real discovery worth remembering

`studies.tsv` (owned by the `download_metadata` role) can lag behind the
`studies/` directories it's already created. Confirmed directly against
the live collection on 2026-09-05: `studies.tsv` had 22 rows while
`studies/` had 41 real directories, each with a proper `README.md`.
`build_catalog.py` treats the **directory listing** as the authoritative
set of studies (`sources.list_study_ids`), falling back to parsing a
study's `README.md` header (`sources.load_readme_header`) for any study
missing its `studies.tsv` row, rather than silently dropping it from the
catalog. Don't assume `studies.tsv` alone is complete in future work here.

## Environment notes

- **Python version**: HTCF's default `python3` (`/usr/bin/python3`) is
  3.6.8 and cannot run this code (dataclasses + `from __future__ import
  annotations` need 3.7+). Use the project's own venv,
  `/ref/rmlab/software/azamat/als_pipeline_env/bin/python3` (3.11.8) — this
  is also where `boto3` was installed for this project (2026-09-05).
- **Login node etiquette**: `/lts` is only mounted on HTCF's login node, so
  this all necessarily runs there. `build_catalog.py`/`s3_sync.py --dry-run`
  are lightweight (metadata reads, no file hashing in dry-run mode — see
  below) and fine interactively. A real `s3_sync.py`/`publish.py` run
  without `--dry-run` hashes and uploads real (sometimes multi-GB) files —
  if that ever becomes heavy enough to matter, run it via `srun
  --partition=interactive` rather than directly on login, per the same
  practice `hpc/setup_sc_env.sh` already documents for this collection.
- **Dry-run performance**: `s3_sync.py --dry-run` does **not** hash file
  contents — only `s3_sync.py`'s real (non-dry-run) path does, since
  hashing every eligible study's real data files (some multi-GB) is far
  too slow to be a "preview." Found this the hard way: an early version
  hashed everything unconditionally and a real dry run over all 41 studies
  hung past two minutes before being killed; fixed by skipping hashing
  entirely when `dry_run=True`.

## Interim hosting on Vercel, bundled data (2026-09-08)

The user asked for the app to actually be live now, before the S3/CloudFront
infra in `infra/` is provisioned. Since there is no bucket yet, the "live,
no-redeploy" update flow described above isn't wired up end to end — so as
an interim step, this deploy bundles a **snapshot** of `catalog.json`/
`samples.json` into the Vercel build (`web/public/data/`) rather than
fetching from S3. This is a deliberate, temporary departure from the
"metadata lives in S3" design, not a replacement for it.

- **Account**: a brand-new Vercel account (`azamat-7178`), created fresh for
  this project per the isolation requirement — never neurodegen-commons'
  account/deployment. Vercel's current signup flow doesn't offer a bare
  "personal account" scope; every account operates inside a team construct,
  and the "group name" prompt at signup created a team called `mgi5`
  ("MGI"). Checked `vercel teams members` and confirmed it has exactly one
  member — `azamat-7178`, OWNER — so despite the name, this is not a
  pre-existing shared/lab team; it behaves as a personal workspace.
- **Live URL**: https://als-dataset-browser.vercel.app (aliased; the
  per-deploy URL changes each time, the `.vercel.app` alias doesn't).
- **Deploy command**: `cd web && vercel deploy --prod --yes --name
  als-dataset-browser` from this machine, authenticated via `vercel login`.
- **Refresh procedure until S3 is live** (repeat before each deploy):
  1. On HTCF: `cd data_web_browser/pipeline && $PY build_catalog.py --root
     /lts/rmlab/rmlab_shared3/BioMiners/EXTERNAL_DATASETS
     --coordination-root /lts/rmlab/rmlab_shared3/azamat/als_pipeline_coordination
     --out-dir /tmp/dwb_out_<ts>` to regenerate against current source data.
  2. `scp` `catalog.json`/`samples.json` down into `web/public/data/`,
     overwriting the bundled snapshot.
  3. `npm run build` (bundles the new snapshot into `dist/`), then
     `vercel deploy --prod`.
- **First real refresh (2026-09-08)**: rebuilt against current HTCF data and
  found `all_samples.tsv` plus 6 studies' `samples.json` had been updated
  since the 2026-09-07 build — another session had backfilled
  `disease_status` for exactly the gap noted in an earlier session (GEO
  titles like "Control 1"/"Control 2" not being parsed into the normalized
  field). Confirmed via diff: `Bryce-Smith2025_GSE296714`, `GSE310722_dataset`,
  `Krach2018_GSE76220`, `Lall2025_CellStemCell`, `Zelic2025_Immunity`, and
  `pTDP43_PNAS2025` all gained real `disease_statuses` values (previously
  `[]`). All 41 studies' `summary` fields were already populated and
  unchanged. Verified the live deployment serves this refreshed data by
  curling `/data/catalog.json` on the production URL directly.
- **Not done as part of this**: no CORS setup was needed (data is
  same-origin, bundled into the Vercel deployment itself, not fetched from
  S3) — this requirement only applies once the app fetches from a separate
  S3/CloudFront origin, per the earlier hosting discussion.

## MCP server (2026-09-09)

Built the previously-parked MCP server: a public, read-mostly remote server
(`mcp_server/`) letting Claude (or any MCP client) search studies/samples,
get comprehensive detail, understand what's inside a specific processed
file, get S3 download links (single-file or bulk-manifest), and queue a
request for a dataset not yet in the collection. Full design discussion,
code, and revisions happened over several rounds with the user before any
of it was written — see the approved plan for the complete reasoning; this
section covers what actually got built and what was learned building it.

**Pipeline schema additions** (the only changes to existing, previously-
tested code) — `catalog_schema.py`/`sources.py`/`build_catalog.py`:
- `StudyRecord.access_restricted: bool` — `True` iff `study_id` is in
  `sources.skipped_study_ids(build_summary)` (currently just the one
  dbGaP-controlled study). **Real correction made while building this:**
  the plan originally assumed a study like this would still appear in the
  catalog with reduced info. In practice `HNSCC_Pembrolizumab_dbGaP` has
  **neither** a `studies.tsv` row **nor** a `studies/` directory (it was
  never downloaded at all) — so it wasn't in `study_ids` to begin with and
  would have silently vanished from the catalog entirely. Fixed by adding
  `sources.build_summary_entry()` and folding `hard_skipped` into the
  `study_ids` union, with a minimal stub row (just `notes`, from
  `build_summary.json`'s own `status` text) for a study with no other
  metadata source at all.
- `StudyRecord.readme_body`, `.series_summaries`, `.conversion_log_raw`,
  `.qc_report` — full README content (minus the title/metadata header),
  original GEO series title/summary/design, the whole `conversion_log.md`,
  and the whole `commons_validate_report.json`, all read once at build time
  so the Lambda never needs HTCF filesystem access (it only ever has S3
  access) or to re-implement any of this parsing.
- `SampleRecord.raw` — original per-sample GEO fields (`characteristics`,
  title, GSM, supplementary_files, etc.) not already covered by the 19
  normalized fields, via `sources.load_raw_samples_by_key()` indexing each
  study's own `samples.json` by `sample_id`/GSM.
- `build_catalog.py` now **requires** `build_summary.json` to exist and be
  non-empty (raises `RuntimeError` otherwise) — before this change a
  missing file only affected an internal sync decision; now it gates
  what's publicly exposed via the MCP server, so a missing file must fail
  loudly rather than silently leaving every study looking unrestricted.

**7 tools, 5 resources** (`mcp_server/tools/*.py`, `mcp_server/resources/*.md`):
`search_studies`, `get_study_overview` (batch, comprehensive — full
README, original GEO series info, per-study samples up to a 100-row cap),
`search_samples` (cross-study, capped at 50), `get_sample_details` (raw +
normalized, per-sample), `explain_data_file` (format + this file's own
conversion-log section + QC report entry), `get_download_links` (presigned
URLs directly for ≤5 files, else one manifest-file link for more —
threshold chosen with the user), `request_dataset_download` (queues a
not-yet-collected dataset in `requests/download_next.json`, using S3
conditional writes to survive concurrent requests safely). Resources are
curated, user-facing reference docs — the h5ad/layers schema, the bulk
RNA-seq Parquet+TSV convention, DecontX methodology, alignment methodology,
the normalized sample-metadata field reference — condensed from
`PIPELINE_INSTRUCTIONS.md`/`ALIGNMENT_INSTRUCTIONS.md`/
`schema/metadata_dictionary.md` with the debugging narrative and per-study
one-off exceptions deliberately left out (those live in `explain_data_file`
instead).

**Resource-link content blocks, per user request:** tools that return
schema-sensitive data (all of them except `request_dataset_download`)
attach real MCP `resource_link` content blocks (`mcp_server/resource_links.py`)
pointing at the relevant resource(s) — not just a plain string field buried
in JSON — so a client sees "here's a reference for this" in the same
response, without having to notice and parse a URI out of structured data.

**Transport:** `mcp` Python SDK v2 (`MCPServer`, formerly `FastMCP` in v1 —
the v1→v2 rename/API changes were discovered mid-build, not assumed), zip-
deployed Lambda via the AWS Lambda Web Adapter, public Function URL
(`authorization_type = "NONE"`), `stateless_http=True` + `json_response=True`
since every Lambda invocation is a fresh, self-contained request. No
container/ECR, no API Gateway.

**Two boto3 identities** (`mcp_server/s3_clients.py`) — the Lambda's own
execution role for everything except presigning, and a separate long-lived
IAM user read from SSM for `generate_presigned_url` calls specifically,
because a presigned URL signed with Lambda's own temporary STS credentials
expires when that STS session does, regardless of the requested `ExpiresIn`
— well under the 24h TTL download links need.

**Real bugs found only by actually running this against the real `mcp`
SDK** (not caught by mocked unit tests — see the "verification" note
below for why both layers of testing mattered here):
- `mcp.resource()` rejects **any** declared parameter on a non-templated
  resource, even one with a default value — the common
  `def _reader(p=path): ...` closure-over-loop-variable idiom doesn't work
  here. Fixed with a proper zero-arg closure factory (`_make_reader`).
- `ResourceLink`'s real field is `mime_type` (snake_case), not `mimeType` —
  caught once real objects were actually constructed and inspected.
- `mock.patch('server.MCPServer')`-style tests are fundamentally broken for
  this file: the patch's own target-resolution step imports `server` fresh
  (since it wasn't in `sys.modules` yet), running all of its module-level
  registration code for real *before* the mock is swapped in — so every
  assertion against the mock sees nothing happened. Rewrote `test_server.py`
  as a small integration test against the real imported module instead of
  fighting this timing trap.
- A cross-test-file pollution bug: `test_get_download_links.py`'s fixture
  did `del sys.modules['s3_clients']` on teardown instead of restoring
  whatever was there before — this orphaned `test_s3_clients.py`'s own
  already-bound module reference (imported at collection time) once
  `mock.patch('s3_clients.boto3')`'s own target-resolution re-imported a
  *different* module object under the same name. Fixed to save/restore the
  original `sys.modules` entries rather than deleting them.
- `explain_data_file`'s QC-entry matching used to be a raw substring check
  (`filename in path`), which could match the wrong entry if one file's
  name happened to be a substring of another's path. Fixed to compare
  basenames exactly.
- `strip_known_extension()` was added to `format.py` after discovering the
  original naive `filename.rsplit(".", 1)[0]` under-strips real compound
  extensions in this collection (`.tsv.gz`/`.csv.gz`/`.mtx.gz`), which
  `explain_data_file`'s conversion-log section matching depends on.

**Verification, real not mocked:** 222 unit tests (`mcp_server/tests/`,
`mcp` and `boto3` real and installed, only their I/O-performing calls
mocked) plus an actual local server run (`uvicorn`) against
`mcp_server/fixtures/` — a trimmed **real** 3-study slice of the HTCF
collection (Zelic2025_Immunity, a bulk-only study, and the access-restricted
study), driven with the real `mcp` client SDK end to end: `tools/list`,
`resources/list`, `resources/read`, and every tool call except the two that
genuinely require real AWS (`get_download_links`, `request_dataset_download`
— both correctly fail with a real `ParameterNotFound`/similar at exactly
the point real infrastructure would be needed, confirmed by reading the
actual server-side traceback rather than assuming). Also confirmed
`mcp_server/build.sh`'s manylinux packaging produces a real Linux x86_64
`pydantic_core` binary — confirmed by observing it correctly *fails* to
import on this Mac's arm64 interpreter, which is the expected, correct
outcome for a foreign-platform compiled wheel (it can only actually run
inside Lambda's own Linux runtime).

**Infra** (`infra/mcp.tf`, additive only): Lambda + Function URL + public-
invoke permission, the Lambda execution role, the separate presign IAM
user + SSM parameter (seeded manually post-`apply`, never via
`aws_iam_access_key` — that would put the secret in Terraform state), and
a 3-day lifecycle rule expiring `manifests/*`. Validates cleanly
(`terraform validate`).

## Real deployment (2026-09-09/10)

Applied for real: bucket `rmlab-als-dataset-portal` (us-east-2), CloudFront
`d1vro9p4q8lq6g.cloudfront.net`, MCP Lambda + Function URL, both IAM
identities. AWS account: `340752797701` (IAM user `azamat`, this project's
own account — nothing shared with neurodegen-commons). 16 resources created
in one `terraform apply`; the presign IAM user's access key was created and
seeded into its SSM parameter as a one-time manual step, chained directly
from `aws iam create-access-key` into `aws ssm put-parameter` in one script
so the raw secret was never displayed or written to a file that outlived
the command.

**Two more real bugs found only by actually exercising the live, deployed
server** — on top of the ones already found via local fixture testing (see
above). Both are the kind of thing no amount of mocked unit testing would
have caught, since they only manifest against a real public hostname and a
real non-us-east-1 bucket region:

1. **DNS-rebinding protection rejected every real request.** `mcp`'s
   `streamable_http_app()` auto-enables DNS-rebinding protection whenever
   `host` isn't explicitly passed (defaulting to `"127.0.0.1"`), which then
   only allows Host headers matching `127.0.0.1`/`localhost`/`::1` --
   rejecting the real Function URL hostname with `Invalid Host header` / 421.
   Caught via CloudWatch logs after the very first live request. Fixed by
   passing `host="0.0.0.0"` in `server.py` (matching how it's actually
   bound) — DNS rebinding is a threat model for a local dev server a
   malicious webpage could redirect a browser to, not a Lambda Function URL,
   which is only ever reached over its own real HTTPS hostname.

2. **Presigned download URLs were broken for a non-us-east-1 bucket.**
   `boto3.client("s3", region_name="us-east-2")` alone still built
   presigned URLs against the legacy global `bucket.s3.amazonaws.com` host
   -- confirmed directly (not assumed) by generating a URL and inspecting
   it. Following that URL got a real S3 307 redirect to the true regional
   host, and re-requesting at the redirected host broke the query-string
   signature (SigV4 signs over the original Host, so a different Host
   invalidates it) -- confirmed by actually downloading through it and
   getting a 403. Chased through several wrong hypotheses (tried explicit
   `endpoint_url`, which fixed the host but still 403'd; then isolated that
   a plain HEAD request against a GET-signed URL is *itself* a red herring
   worth knowing about, since a presigned URL's signature covers the HTTP
   method too) before finding the actual fix: `presign_client()` needs
   `Config(s3={"addressing_style": "virtual"})` to force
   `generate_presigned_url()` to build the correct regional-host URL
   up front. Verified for real: downloaded an actual 13MB parquet file
   through a live presigned URL with zero redirects.

**Real data published.** Ran `pipeline/publish.py` for `Zelic2025_Immunity`
only (~7.5GB across 3 h5ad + 4 bulk-RNA-seq files) -- not the ~38 studies
that were technically "eligible," since the user asked for one specific
study. This required adding `--only` to `publish.py` (mirroring
`s3_sync.py`'s existing `--only`, which `publish.py` itself didn't expose
before this) rather than either publishing far more than requested or
hand-rolling a one-off script outside the normal pipeline path. Verified
with a `--dry-run` first (confirmed exactly 1 eligible study, the right 7
files) before running for real. HTCF itself has no AWS credentials
configured -- the real publish run required passing the same local
credentials through as environment variables for that one SSH command
only, never written to a file on the shared machine.

**End-to-end verification actually completed**, not just claimed: live MCP
server → `search_studies` returns the real published study →
`get_download_links` returns a real presigned URL → that URL downloads a
real Apache Parquet file with `curl`, confirmed via `file`. This is the
first real, working, publicly-reachable piece of this whole project.

**A third real bug, caught by the user actually using the live server, not
by any of the above verification:** `search_studies`/`get_study_overview`
reported `data_formats`/`processed_files` for all 39 studies that have real
converted data *on HTCF*, regardless of whether that data was ever synced
to S3 -- so calling `search_studies` right after publishing only
`Zelic2025_Immunity` made it look like 39 studies were downloadable, when
only 1 actually was. Root cause: `processed_files`/`data_formats` were
built from the catalog's full local file listing, never checked against
`s3_key`/`available_externally` (the field `build_catalog.py` already
computes as ground truth against live S3 state -- it just wasn't being
read here). Also surfaced two tools had **no test coverage at all**
(`search_studies.py`, `get_study_overview.py` -- an oversight from earlier
in the build, never caught since the hook-generated test suite happened to
skip exactly these two files). Fixed by adding an explicit
`available_externally` boolean at the study level (both tools) and a
`downloadable` boolean per file (`get_study_overview`), with docstrings
now stating plainly that a non-empty `data_formats` does NOT imply
downloadability -- plus 12 new tests for both tools, including a direct
regression test for this exact scenario (a study with real local files and
`s3_key: None` must report `available_externally=False`). Verified against
the live server: exactly `Zelic2025_Immunity` now reports
`available_externally=True`; all other 38 studies with local data
correctly report `False`.

**A fourth real bug, and the most fundamental one: every tool's real
payload was invisible to the client the user was actually connecting
with.** Every tool followed the same pattern -- a one-line summary
("Found 2 matching studies.") in `content` (the channel a calling model is
guaranteed to see), with the entire actual result (study lists, sample
details, everything) placed only in `structured_content` (an optional,
additional machine-readable mirror the MCP spec does not require every
client to forward to the model). The client the user was using apparently
never surfaces `structured_content` at all -- so every tool call, from any
angle, returned nothing but a bare count, identically empty whether 1 study
matched or 42. This was systemic across all 7 tools, not a bug in any one
of them, and had gone completely unnoticed through every round of
verification in this project so far (unit tests check `structured_content`
directly, and the local/live checks done here always inspected
`result.structured_content` too -- never `result.content[0].text` the way
an actual chat client would).

Fixed with one shared helper, `mcp_server/tool_response.py`'s
`build_result(summary, data, extra_content=None)`, used by all 7 tools: it
JSON-serializes the same `data` dict directly into the `TextContent` block
(right after the summary line), in addition to still setting
`structured_content` for clients that do use it. This makes every tool's
result self-sufficient regardless of what a given client does with the
optional channel. 23 new tests for the helper itself, plus every tool's
existing tests updated to match (mostly changing exact-text assertions to
prefix checks, since the text block now carries the summary followed by
the full JSON body). Verified against the live server directly: a real
`search_studies` call's `content[0].text` now contains the full list of
19 matching studies with all their fields, not just a count.

## Honest limitations

- The web app's sample table caps at 200 rows per study client-side purely
  for render performance — there's no pagination yet for studies with more
  samples than that (e.g. `Pineda2024_Cell` has 154).
- `samples.json` is currently ~4MB uncompressed (5,964 sample rows across
  41 studies) and is fetched in full on every page load. Fine at this
  scale (loads in well under a second locally); would be worth lazy-loading
  per-study if the collection grows an order of magnitude.
- No tests exist for the `web/` frontend (JS) — only the Python `pipeline/`
  has a test suite. The frontend was instead verified by an actual
  `npm run build` + running the built app against the real catalog
  generated from HTCF (see README's verification section).

## Canonical vocabulary columns and 4 new/updated filters (2026-09-11)

The 2026-09-06/07 fix above (case-fold + dedupe-joined) was deliberately
*mechanical* -- it never merged values that differed by more than
formatting, so real synonyms like `Control`/`CTL`/`ALS (C9orf72)`/`C9-ALS`
stayed as separate facet options. On 2026-09-11 the upstream HTCF
collection's own `download_metadata` role ran a much deeper, manually
reviewed vocabulary-normalization pass across the whole corpus (documented
in `EXTERNAL_DATASETS/vocabulary/CHANGES.md` and `genotype_CHANGES.md` --
worth reading in full for the exact reasoning behind every non-mechanical
merge, including several explicitly confirmed with the user rather than
guessed). It added four new, **additive-only** columns to `all_samples.tsv`
(and every study's `samples.json`), leaving the original raw columns
byte-for-byte untouched:

- `disease_status_canonical` -- 51 raw `disease_status` values collapsed to
  16 clinical categories + null. Genetic-subtype detail (C9orf72/SOD1/FUS/
  TARDBP) is deliberately *not* folded in here -- it lives in `genotype`
  instead, by design.
- `tissue` + `cell_type` -- `tissue_or_cell_type`'s 86 raw values, split
  into a real anatomical-region field and a real cell-population field
  (the old field was NOT a consistent "tissue; cell_type" pattern -- each
  compound value needed individual review, e.g. `"skin; iN"` is a donor
  biopsy origin plus an in-vitro-reprogrammed cell type, not a tissue and
  a sorted subpopulation of it).
- `genotype_canonical` -- a separate follow-up pass; also fixed real
  wrong-field data along the way (233 rows where a GEO depositor had put a
  disease-status/treatment label under the `genotype` characteristic key;
  111 of those cleared/moved, 122 left as a documented, unresolved
  depositor-side bug -- bare numeric values in `GSE329677_dataset` that
  don't match donor age from the source paper and couldn't be explained).

This repo's pipeline just reads these four columns through, the same way
it already read `genotype` -- no additional canonicalization logic needed
here, since the merging work already happened once, corpus-wide, on HTCF:

- `catalog_schema.py`: `SampleRecord` gained
  `disease_status_canonical`/`tissue`/`cell_type`/`genotype_canonical`
  (mirroring the new TSV columns, defaulting to `None`). `StudyRecord`
  gained the study-level aggregates `disease_statuses_canonical`/
  `tissues_canonical`/`cell_types`/`genotypes_canonical` (each a sorted
  `list[str]` of the distinct non-null values across that study's samples,
  appended at the end of the dataclass with `default_factory=list` so
  existing callers that construct a `StudyRecord` positionally/by keyword
  without them still work).
- `build_catalog.py`'s `build()` aggregates the four new study-level lists
  directly from `all_samples.tsv` rows (no case-fold/dedupe step needed,
  unlike `disease_statuses`/`tissues` -- these columns are already
  deduped). `build_sample_records()` passes the four new per-sample values
  through unchanged.

**Web app changes** (`web/src/facets.js`, `FilterSidebar.jsx`, `App.jsx`,
`StudyDetail.jsx`): the "Disease status" and "Tissue" filters now filter on
the canonical fields (`disease_statuses_canonical`/`tissues_canonical`)
instead of the raw ones -- same sidebar labels, but a much shorter, real
list of options (16 vs. 46 for disease status). The raw values aren't
hidden: `StudyDetail`'s per-sample table still shows the original
`disease_status`/`tissue_or_cell_type` text exactly as before, plus a new
`genotype` column. Two new filters were added the same way: "Cell type"
(`cell_types`) and "Genotype" (`genotypes_canonical`).

**Filter combination logic** (confirmed against the existing
`filterStudies` implementation, unchanged by this work): within one facet
group, multiple selected values are OR'd (`matchesArrayFacet`'s `.some()`)
-- e.g. selecting two assay types matches a study with *either*. Across
different facet groups, it's AND (`filterStudies` short-circuits `false`
per group) -- e.g. assay type + tissue both selected narrows to studies
matching both. This was already the design before today's change; adding
`cell_type`/`genotype` as two more `matchesArrayFacet` calls in the same
function was all that was needed.

**Verified end-to-end against real HTCF data**, not just fixtures: synced
the updated `pipeline/` files to the HTCF-side deployment copy at
`EXTERNAL_DATASETS/data_web_browser/pipeline/`, ran `build_catalog.py`
there for real (`python3.9`, no `--bucket` -- confirmed the web app never
actually reads `available_externally`/`s3_key` anywhere, so the S3-live
merge doesn't matter for this bundled-data deploy), copied the resulting
`catalog.json`/`samples.json` into `web/public/data/`, ran `npm run build`
successfully, and drove `facets.js` directly against the real catalog data
to confirm the OR-within-group/AND-across-group behavior holds (e.g.
selecting 2 assay types + 1 tissue narrowed correctly, verified against
every matching study by hand). 268/268 pipeline tests pass.

**Deployed to Vercel the same day**, then rebuilt/redeployed again on
2026-09-11 after a second upstream metadata refinement pass (same schema,
refined values -- no pipeline code changes needed, just
`build_catalog.py` re-run + `npm run build` + `vercel deploy --prod`).
Live at https://als-dataset-browser.vercel.app.

## MCP server deprecated (2026-09-14)

The user decided the MCP server is no longer relevant to this project's
direction -- development and use of it stop here. The code stays in the
repo (`mcp_server/`, `infra/mcp.tf`) as a reference/for potential future
revival, but should not be extended or treated as a maintained component.
`mcp_server/README.md` and the directory-layout note above carry the same
notice. The deployed AWS Lambda + Function URL + IAM user + SSM parameter
(see "Real deployment" above) are being **left running, deliberately**:
checked `infra/mcp.tf` for real cost drivers (no NAT gateway, no VPC, no
provisioned/reserved concurrency) and confirmed an idle Lambda + Function
URL costs effectively $0/month (pay-per-invocation; the only always-on
cost is negligible CloudWatch Logs storage from past invocations). The one
non-cost argument for tearing it down -- the Function URL is a public,
unauthenticated (`authorization_type = "NONE"`) endpoint with no one
maintaining it -- was raised and the user chose to leave it as-is rather
than destroy it, since the sole reason under consideration (cost) doesn't
apply. Revisit with `terraform destroy -target=<mcp.tf resources>` if that
changes.

## MCP server reactivated in code, not yet redeployed (2026-09-18)

The user decided the MCP server should be functional again, with one
change: **it must never hand out a copy of any file** -- no presigned S3
URLs, no manifests. `get_download_links` was removed and replaced with
`get_data_locations`, which returns the real HTCF filesystem path a
study's processed data lives at (`<source_root>/studies/<study_id>/processed/`,
read straight out of the already-cached `catalog.json`'s own `source_root`
field -- no new HTCF access needed from the Lambda). This is useful to
someone with real HTCF filesystem access (a lab member, or a Claude Code
session running on HTCF); it was never a way to fetch data *through* this
server, so nothing is lost by never offering a URL.

Removed along with it, since nothing needs it anymore: `s3_clients.py`'s
`presign_client()` and the whole long-lived `mcp_presign` IAM
user/SSM-parameter apparatus it depended on (`infra/mcp.tf` updated to
match -- one execution role now, not two identities); the manifest
threshold/TTL env vars; the `manifests/` S3 lifecycle rule. 6 of `mcp_server/`'s
docstrings still referenced the removed tool by name (stale
cross-references, e.g. "use get_download_links next") -- caught and fixed
while answering an unrelated question about the sample-detail view.
`mcp_server/README.md` and the directory-layout note above no longer carry
the deprecation notice. 229/229 `mcp_server` tests pass.

**Real discovery: this checkout's local Terraform state is gone.**
Neither this repo's `infra/` nor the original scratchpad session that ran
the first real `terraform apply` still has a `terraform.tfstate` file (the
scratchpad's survived only as a stale provider cache, no state). Running
`terraform apply` here blindly would make Terraform think none of these
resources exist and try to create duplicates. Not resolved yet --
flagged so no future session (including a later me) applies blindly.

**Not yet deployed.** The rebuilt `mcp_server/build/` package exists
locally (`./build.sh` already run) but was never pushed to the real Lambda
-- the live function still runs the old `get_download_links` code as of
this writing. Deploying for real needs either (a) direct `aws lambda
update-function-code`/`update-function-configuration`/`iam put-role-policy`
calls (bypassing Terraform given the state gap above), or (b) reconstructing
Terraform state via `terraform import` first. Either way, an explicit
go-ahead is needed before touching the live function -- not given yet.

## HTCF metadata refresh: 41 -> 50 studies, plus a real parser bug fix (2026-09-19)

`all_samples.tsv`/`studies.tsv` were updated on HTCF again (9 new study
directories appeared). Rebuilt `catalog.json`/`samples.json` from the live
collection the same way as the 2026-09-11 refresh (HTCF-side `python3.9
build_catalog.py`, no `--bucket` since the web app never reads
`available_externally`/`s3_key`) -- 50 studies, 6,192 samples. Copied into
`web/public/data/` **locally only**, not deployed to Vercel yet (explicit
instruction this round: make it locally, commit, don't push).

**Real bug found and fixed while re-verifying an external review's claims
(see next section) against this fresh data:** `sources.split_multi()`
treated a cell as "no value" only on an *exact* case-insensitive match to
`"NONE"`. `Pineda2024_Cell`'s `studies.tsv` `gse` cell is actually `"NONE
(SRA-only deposit, no GEO series)"` -- close, but not an exact match, so
the whole sentence became that study's sole `gse` list entry: a
plausible-looking but fake accession that would break any accession-based
join or parser downstream (exactly the failure mode the external review's
A3 flagged, independently, against an earlier snapshot). Fixed by matching
`value.upper().startswith("NONE")` instead of exact equality -- verified
directly against the real rebuilt catalog: `Pineda2024_Cell.gse` is now
`[]`, correctly.

**New filter option: "(not recorded)".** Turned an information-only
finding (see "How many studies have no entries..." earlier this session)
into an actual feature: `facets.js` now adds a `(not recorded)` sentinel
option to any facet where at least one study has a genuinely empty array
for that field (currently: disease status and tissue -- organism/assay
type never are). Selecting it matches studies with zero entries, via the
same OR-within-group/AND-across-group logic every other facet value
already uses (`NOT_RECORDED` is just one more value `matchesArrayFacet`'s
`.some()` can match against, with `arr.length === 0` as its special-case
comparison). Deliberately distinct from a literal `"Unknown"` value, which
means the source data explicitly recorded "unknown" -- not that nothing
was recorded at all. `matchedFacetValues` (the row-tag feature) handles it
the same way, so a matched study missing that field shows a
`(not recorded)` tag rather than no tag at all.

## External MCP server review, 2026-09-19: findings verified, plan drafted, nothing implemented yet

A third-party hands-on review of the (reactivated) MCP server
(`/Users/azamat/Downloads/als_server_review.md`) came in the same day as
the HTCF refresh above -- worth noting its own numbers (42 studies) predate
both the 2026-09-11 canonical-vocabulary columns and today's 41->50 study
jump, so some specific counts it cites are stale even though the
underlying *problems* mostly aren't. Per explicit instruction: suggestions
and a plan only here, no `mcp_server/` code changes.

### Re-verified against the current, fresh 50-study catalog

- **A3's accession bugs are still real.** `Liu2019_CellReports_GSE126543`'s
  own `gse` list is `["GSE126541", "GSE126542"]` -- the accession in the
  study_id itself (GSE126543) appears in neither. `Pineda2024_Cell`'s fake
  "NONE (SRA-only deposit...)" pseudo-accession was real and just got fixed
  above (a pipeline/parsing bug on this repo's side, not an MCP-layer
  issue). Both are still open, real problems.
- 2 studies still have no `year`; 30 of 50 have no `pmid` (Asano2025
  reproduced exactly as the review describes: a DOI that resolves, `pmid`
  still null).
- Tissue/disease sparsity is real but the review's raw framing overstates
  it slightly: of the ~15-21 studies with an empty *tissue* field, most
  (verified individually) correctly have that information in `cell_type`
  instead (in-vitro/cultured material has no anatomical tissue -- see the
  2026-09-11 vocabulary section) rather than missing it outright. Disease
  status has no such explanation -- empty there really does mean nothing
  was recorded.

### Assessment of the review's own proposals (D1-D10), and where I disagree

Mostly right, roughly in the priority order given. Two places worth a
different call before anyone implements this:

- **B1 ("prose-wrapped JSON") needs to NOT simply become "structured
  content instead of text"**, unlike the review's framing suggests.
  `tool_response.build_result()` already sets `structured_content` on
  every response (see the 2026-09-10 "fourth real bug" section) --
  *and deliberately, redundantly* also embeds the same JSON in the text
  block, because a real connected client (`als-datasets-mgi`) was
  confirmed to not surface `structured_content` at all. If this reviewer's
  own client is doing the same string-surgery workaround the review
  describes, that's independent evidence for the same finding, not a
  reason to remove the text-embedded copy -- doing so would silently
  break that real client again. The right fix is narrower: make the
  *text* format easier to parse (e.g. fence the JSON block, or put
  resource-link mentions somewhere that can't land mid-parse) while
  keeping both channels populated. Worth confirming directly whether the
  reviewer's client can already read `structured_content` before
  concluding text-embedding should go away at all.
- **D7's collapse to one `access` enum** is good but should fold in the
  actual current state, not the review's slightly-earlier one: today it's
  effectively `htcf_processed_path` (via `get_data_locations`, works
  regardless of S3 state) vs. nothing, since presigned downloads no longer
  exist at all post-reactivation -- `public_s3` may not even be a
  meaningful enum value anymore depending on whether the S3 mirror concept
  survives the "no downloads" decision. Worth deciding that scope question
  before building the enum.

### Proposed phased plan (not implemented)

**Phase 1 -- cheap, high-value, no schema changes:**
1. D1 `describe_catalog`/facet endpoint (fixes B2, B3's exploratory-cost
   complaint, and doubles as A2's "what are the valid filters" discovery
   mechanism).
2. A2: reject unknown `search_samples` parameters explicitly (or echo
   `ignored_parameters`) -- small, contained, prevents silent
   over-return.
3. A1: `offset`/`limit` on `search_samples` and `get_study_overview`'s
   sample block -- the current 100/50 caps make the 3 largest cohorts
   (~68% of the collection by sample count) partially unreachable.
4. Fix the two verified accession bugs (Liu2019, and confirm no other
   `studies.tsv` rows have the same class of problem) -- a `studies.tsv`
   edit on HTCF, not an MCP-layer fix; needs the right accession confirmed
   against the actual paper/GEO record before touching it, same care the
   2026-09-11 vocabulary work used.

**Phase 2 -- real value, more design work:**
5. D3 `genotype` as a first-class, normalized `search_samples` filter
   (HGNC symbol + free-text allele) -- for an ALS collection this is
   arguably a bigger gap than anything else on the list, since mutation
   status is the primary stratifier and today it only exists in per-sample
   detail calls.
6. D4 `get_design_table(study_id)` -- directly answers B5's Asano2025
   example (3x2x3 design invisible in the lean view).
7. D7 access-model collapse, once the scope question above is resolved.
8. B7's `assay_types` normalization (16 raw strings across 50 studies,
   including compound values no filter will match) -- same kind of
   reviewed, not-mechanical vocabulary work as the 2026-09-11 disease/tissue/
   genotype pass, ideally done the same way (a dedicated pass with
   explicit user sign-off on ambiguous merges), not invented ad hoc here.

**Phase 3 -- bigger scope, real design decisions needed first:**
9. D5 gene-level query/presence -- highest ceiling, but needs a real
   design decision (precomputed presence bitmap vs. live per-sample
   query) before estimating effort.
10. D8 `build_cohort` -- natural endpoint once D3/D4/D5 exist, not before.
11. D9 curation tags (`ALS cohort` vs `comparator` vs `off-topic`) and
    `get_request_status` for the download-request queue -- both
    self-contained, could happen anytime, just lower urgency than the
    above.
12. D6 structured file inventory (promote `conversion_note` prose to typed
    fields) -- valuable but touches the conversion pipeline's own output
    format, bigger blast radius than anything else on this list.

## Not yet done

- **Switching the live app from bundled data to a live S3 fetch.** The web
  app is deployed to Vercel (see "Interim hosting on Vercel" above) but
  still reads a bundled snapshot, not S3 — every metadata change currently
  requires a manual rebuild + redeploy, not the "automatic, no redeploy"
  behavior the original design calls for. AWS is provisioned now (see "Real
  deployment" above), so this is unblocked — switch to
  `VITE_METADATA_BASE_URL` pointing at the CloudFront/S3 metadata prefix
  and drop `web/public/data/` whenever the user wants to do this.
- **Publishing the rest of the eligible studies.** Only `Zelic2025_Immunity`
  has been published for real so far, at the user's specific request (not
  all ~38 that are technically eligible) — see "Real deployment" above.
  Publishing more is just `publish.py --only <ids>` (or no `--only` at all
  for everything eligible) — a normal operational action at this point, not
  a new infrastructure decision.
- **Adding `s3_publish` to `PROTOCOL.md`'s role table** — see Coordination
  above.
