// Builds the plain-text blob the "Copy information for Claude" button in
// StudyDetail puts on the clipboard -- study identity/summary plus the real
// filesystem location of its processed data on every system it lives on
// (HTCF and RIS), for pasting into a Claude Code session that has access to
// either one. Deliberately study-level only
// (no per-sample paths): processed files hold every sample together in one
// file (see mcp_server/resources/h5ad_schema.md's obs["sample_id"]
// convention), and raw per-sample files are bundled inside one
// <GSE>_RAW.tar per series on HTCF -- neither has a meaningful standalone
// per-sample path to hand someone.

const MAX_LISTED_FILES = 20

const SYSTEM_LABELS = { htcf: 'HTCF', ris: 'RIS (Compute2 / Storage3)' }

// `roots` is catalog.roots: { htcf: <abs root>, ris: <abs root> }. The layout
// below each root is identical, so one study maps to one path per system.
export function buildStudyContext(study, roots) {
  const lines = []
  lines.push('ALS Dataset Browser -- study context')
  lines.push('')
  lines.push(`Study: ${study.study_id}`)
  const accession = (study.gse || [])[0] || study.bioproject || study.cellxgene_collection || study.synapse
  if (accession) lines.push(`Accession: ${accession}`)
  if (study.title) lines.push(`Title: ${study.title}`)

  const tags = [
    study.organisms?.length && `Organism: ${study.organisms.join(', ')}`,
    study.disease_statuses_canonical?.length && `Disease status: ${study.disease_statuses_canonical.join(', ')}`,
    study.tissues_canonical?.length && `Tissue: ${study.tissues_canonical.join(', ')}`,
    study.assay_types?.length && `Assay: ${study.assay_types.join(', ')}`,
    study.n_samples != null && `Samples: ${study.n_samples}`,
  ].filter(Boolean)
  if (tags.length) lines.push(tags.join(' | '))

  if (study.summary) {
    lines.push('')
    lines.push(`Summary: ${study.summary}`)
  }

  lines.push('')
  const dataFiles = (study.processed_files || []).filter((f) => f.category === 'data')
  const systems = Object.entries(roots || {})
  if (dataFiles.length > 0 && systems.length > 0) {
    lines.push('Processed data (same layout on each system -- use the path for the system you are on):')
    for (const [system, root] of systems) {
      lines.push(`${SYSTEM_LABELS[system] || system}: ${root.replace(/\/+$/, '')}/studies/${study.study_id}/processed/`)
    }
    lines.push('Files:')
    for (const f of dataFiles.slice(0, MAX_LISTED_FILES)) {
      lines.push(`  - ${f.name}`)
    }
    if (dataFiles.length > MAX_LISTED_FILES) {
      lines.push(`  (+ ${dataFiles.length - MAX_LISTED_FILES} more -- see the directories above)`)
    }
  } else {
    lines.push('Processed data: not yet processed for this study.')
  }

  return lines.join('\n')
}
