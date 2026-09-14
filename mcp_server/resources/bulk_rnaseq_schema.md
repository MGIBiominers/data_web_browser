# Bulk RNA-seq file structure (this collection)

Bulk RNA-seq data is never converted to AnnData/h5ad -- it's kept as
Parquet + TSV, samples as rows and genes as columns.

Typical file set per bulk study (naming:
`<study_id>_bulk_<series_tag>_<kind>.<ext>`):
- `..._counts.parquet` / `..._counts.tsv.gz` -- raw/deposited counts
  (primary table).
- `..._normalized.parquet` / `.tsv.gz` -- TPM/RPKM/FPKM, when the original
  submitters deposited it (a separate table, never mixed into counts).
- `..._metadata.tsv` -- per-sample metadata, joined by `sample_id`.
- Gene identifiers are Ensembl IDs with the version suffix stripped for
  joining; a companion `gene_id_versioned` column preserves the original ID.

Some studies' source data couldn't be resolved to real sample identifiers
(e.g. anonymized column headers with no corresponding GEO metadata) -- when
that happened, affected per-sample metadata fields are set to the literal
string `"UNRESOLVED_GSM_MAPPING"` rather than guessed. Check
`explain_data_file` for whether this applies to a specific file.
