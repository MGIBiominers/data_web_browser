# From raw sequencing reads to a count matrix (alignment)

For studies where this collection started from raw FASTQ rather than an
already-processed matrix, alignment runs via a Nextflow pipeline
(10x/CellRanger for single-cell/single-nucleus and multiome data),
producing the standard 10x-format output (`filtered_feature_bc_matrix.h5` /
`raw_feature_bc_matrix.h5`) that the conversion step then reads.

Before alignment, each study's sequencing chemistry (10x v2/v3, single vs.
dual index, expected read structure) is confirmed against the original
paper and/or raw FASTQ headers -- never assumed from the platform name
alone.

For exact parameters, reference genome, or per-sample exceptions for a
specific study, use `explain_data_file` or `get_study_overview`.
