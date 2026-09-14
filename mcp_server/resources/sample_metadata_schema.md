# Normalized sample metadata fields

Every sample (via search_samples/get_sample_details) is normalized to the
same fixed field set, regardless of source: `study_id`, `accession`,
`sample_id`, `assay_type`, `sample_source`, `organism`,
`cell_line_or_donor`, `genotype`, `disease_status`, `tissue_or_cell_type`,
`timepoint_or_age`, `treatment`, `sex`, `platform`, `batch`, `file_names`,
`is_filtered`, `source_doi_or_pmid`, plus a few study-specific `extra_*`
fields used only where relevant.

Values are harmonized where possible (case differences and near-duplicate
wording collapsed) but the underlying vocabulary is whatever the source
studies actually used -- "ALS", "sporadic ALS", and "C9orf72" are all real,
distinct disease_status values, not typos of each other.

A null/missing field means the source data didn't report it, not that it
was dropped. Use `get_sample_details` to see a sample's original,
pre-normalization fields if you need to check how a value was derived.
