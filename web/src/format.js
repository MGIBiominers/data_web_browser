// Human-readable file format, derived from the filename extension --
// purely presentational, not a re-implementation of the pipeline's own
// data/doc/metadata `category` classification (see pipeline/sources.py's
// classify_file). The goal here is narrower and more concrete: tell someone
// unfamiliar with the pipeline exactly what they'd get -- "h5ad" or
// "parquet", not the internal "data" bucket label.

const EXTENSION_LABELS = [
  ['.h5ad', 'h5ad'],
  ['.h5mu', 'h5mu'],
  ['.h5', 'h5'],
  ['.parquet', 'parquet'],
  ['.tsv.gz', 'tsv'],
  ['.tsv', 'tsv'],
  ['.csv.gz', 'csv'],
  ['.csv', 'csv'],
  ['.loom', 'loom'],
  ['.mtx.gz', 'mtx'],
  ['.mtx', 'mtx'],
]

export function formatLabel(filename) {
  const lower = filename.toLowerCase()
  for (const [ext, label] of EXTENSION_LABELS) {
    if (lower.endsWith(ext)) return label
  }
  return 'other'
}

// Only "data"-category files count as a processed format a user would
// actually want -- doc/metadata sidecars (conversion_log.md, a validation
// report JSON) aren't a format someone downloads the study for.
export function distinctFormats(processedFiles) {
  const formats = (processedFiles || [])
    .filter((f) => f.category === 'data')
    .map((f) => formatLabel(f.name))
  return Array.from(new Set(formats)).sort()
}
