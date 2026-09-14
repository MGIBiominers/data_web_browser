# Single-cell/single-nucleus h5ad file structure (this collection)

Every `.h5ad` file follows a fixed structure so it can be read the same way
regardless of source study.

## Always present
- `X` -- the primary/working expression matrix (may be normalized/log-
  transformed depending on downstream processing).
- `layers["raw"]` -- pre-filtering integer counts. This is a hard
  requirement: every droplet-based h5ad in this collection has a genuine,
  whole-number-valued `layers["raw"]`, even when `X` has been transformed.
- `obs` columns (one row per cell, joined from this collection's normalized
  sample table): `study_id`, `accession`, `sample_id`, `assay_type`,
  `sample_source`, `organism`, `cell_line_or_donor`, `genotype`,
  `disease_status`, `tissue_or_cell_type`, `timepoint_or_age`, `treatment`,
  `sex`, `platform`, `batch`, `file_names`, `is_filtered`,
  `source_doi_or_pmid`, plus study-specific `extra_*` columns.
- `uns["processing_notes"]` -- free-text notes on filtering/correction
  applied to this specific file.

## Present when ambient-RNA correction (DecontX) was applied
- `layers["decontx_corrected"]` -- DecontX-corrected counts.
- `obs["decontx_contamination"]` -- per-cell contamination fraction (0-1).

## Known naming caveat
An external collaborator tool (`neurodegen-commons`) looks for
`layers["counts"]` or `.raw` rather than `layers["raw"]` -- a known naming
mismatch between this collection and that tool, not a bug in either.

## Multiome files (.h5mu)
Multiome studies use MuData (readable via `mudata`/`muon`) instead of a
single AnnData object, with one modality per assay (e.g. RNA + ATAC), each
following the obs/layers conventions above within its modality.

For the exact provenance of a specific file (what was filtered, DecontX
parameters used, dimensions before/after), use the `explain_data_file` tool.
