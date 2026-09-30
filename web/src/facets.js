// Facet options are always derived from whatever distinct values actually
// appear in the fetched catalog -- never a hardcoded taxonomy -- so the
// browser can't drift out of sync as new studies/values get added. See
// DESIGN.md's "Web app: filters/facets" section.

// Single source of truth for which study field backs each facet key --
// buildStudyFacets, filterStudies, and matchedFacetValues (used to show
// "why did this study match" tags on each row) all key off this same map,
// so a facet can't drift out of sync between the sidebar and the tags.
// disease_status/tissue point at the collection's canonical vocabulary
// (disease_statuses_canonical/tissues_canonical -- deduped centrally on
// HTCF, see DESIGN.md) rather than the raw disease_statuses/tissues
// values, which still carry every spelling variant a source study used.
// The raw values aren't dropped -- they still display per-sample in
// StudyDetail -- this only changes what powers the sidebar checkboxes.
export const FACET_FIELDS = {
  organism: 'organisms',
  assay_type: 'assay_types',
  disease_status: 'disease_statuses_canonical',
  tissue: 'tissues_canonical',
  cell_type: 'cell_types',
  genotype: 'genotypes_canonical',
}

// Sentinel option meaning "this study has zero entries for this facet's
// field" -- distinct from any real value (including a genuine "Unknown"
// disease-status entry, which means the source data explicitly recorded
// unknown, not that nothing was recorded at all). Only offered for a facet
// when at least one study actually has an empty array there, so it never
// shows up as a dead option for e.g. organism/assay_type, which every study
// has.
export const NOT_RECORDED = '(not recorded)'

function distinct(values) {
  return Array.from(new Set(values.filter((v) => v !== null && v !== undefined && v !== ''))).sort()
}

// Two-level grouping for facets whose canonical values naturally cluster
// under a broader umbrella -- e.g. disease_status_canonical now has 12
// distinct "ALS ..." values (ALS, "ALS (rapid progression)", "ALS-FTD",
// "ALS Spectrum MND", ...), which is exactly the collection's own
// vocabulary, not a taxonomy invented here: every child listed below is a
// real disease_status_canonical/tissues_canonical value that already
// exists in the catalog (see the September vocabulary work + the
// 2026-09-2x disease-progression additions). Grouping is presentation-only
// -- it doesn't change what a value means or how filtering matches, only
// how the sidebar organizes the checkboxes. A canonical value not listed
// in any group here just stays a flat, ungrouped top-level option, same as
// before this feature existed.
//
// Deliberately NOT done for genotype: unlike disease_status/tissue/
// assay_type, there's no existing "umbrella" value to group under (e.g.
// nothing named plain "FUS" the way plain "ALS"/"bulk RNA-seq" exist) --
// building one would mean inventing a gene-symbol grouping from scratch,
// the kind of judgment call that needs a dedicated reviewed pass (see
// DESIGN.md), not a quick addition here.
export const FACET_GROUPS = {
  disease_status: {
    ALS: [
      'ALS', 'ALS (fast progression)', 'ALS (non-rapid progression)',
      'ALS (rapid progression)', 'ALS (slow progression)', 'ALS (standard progression)',
      'ALS + cognitive impairment', 'ALS Spectrum MND', 'ALS-FTD',
      'ALS/FTD (pTDP-43 high)', 'ALS/FTD (pTDP-43 medium)', 'ALS/FTD (pTDP-43 negative)',
      'Pre-symptomatic familial ALS carrier',
    ],
    Control: ['Control', 'Healthy Control', 'Non-Neurological Control'],
    'FTD / FTLD': ['FTD', 'FTLD'],
  },
  tissue: {
    'Motor Cortex': [
      'Motor Cortex', 'Motor Cortex (BA4)', 'Motor Cortex (Lateral)',
      'Motor Cortex (Medial)', 'Motor Cortex (Unspecified)',
    ],
    'Frontal Cortex': ['Frontal Cortex', 'Frontal Cortex (BA44)', 'Frontal Cortex (BA46)'],
    'Spinal Cord': [
      'Spinal Cord (Cervical)', 'Spinal Cord (Lumbar)', 'Spinal Cord (Thoracic)',
      'Spinal Cord (Unspecified)', 'Spinal Cord (region unspecified)',
    ],
  },
  // Genuinely combined multi-assay values (e.g. "RNA-seq + ATAC-seq",
  // "scRNA-seq/snRNA-seq") are deliberately left standalone below, not
  // folded into a single-assay group -- they mix two assay types in one
  // string, so no one parent is more correct than another.
  assay_type: {
    'bulk RNA-seq': [
      'bulk RNA-seq', 'bulk RNA-seq (human)', 'bulk RNA-seq (human spinal cord)',
      'bulk RNA-seq (mouse OPC)', 'bulk RNA-seq (siQKI iPSC-MN)',
      'bulk RNA-seq (laser-capture microdissected motor neurons)',
      'bulk RNA-seq (compartmental: axon vs soma)', 'short-read bulk RNA-seq',
    ],
    'scRNA-seq': [
      'scRNA-seq', 'scRNA-seq (Smart-seq2, iPSC-MN)', 'scRNA-seq (iPSC tri-culture)',
      'scRNA-seq (iPSC-MN)', 'scRNA-seq (iPSC-MN, ddSEQ + 10x)', 'scRNA-seq (mouse SOD1)',
    ],
    'snRNA-seq': ['snRNA-seq', 'snRNA-seq (spinal cord)'],
    'long-read RNA-seq': ['long-read RNA-seq', 'long-read RNA-seq (Iso-Seq)'],
    'snATAC-seq': ['snATAC-seq', 'snATAC-seq (multiome)'],
  },
}

export function buildStudyFacets(studies) {
  const facets = {}
  for (const [key, field] of Object.entries(FACET_FIELDS)) {
    const options = distinct(studies.flatMap((s) => s[field] || []))
    if (studies.some((s) => !(s[field] || []).length)) {
      options.push(NOT_RECORDED)
    }
    facets[key] = options
  }
  return facets
}

// Reshapes one facet's flat option list into {standalone, groups} for
// rendering -- groups per FACET_GROUPS above (only children actually
// present in `options` are included, so a group never shows an option
// nothing in the current catalog has), standalone for everything else
// (ungrouped values, plus NOT_RECORDED, always shown flat).
export function buildFacetTree(key, options) {
  const groupConfig = FACET_GROUPS[key]
  if (!groupConfig) return { standalone: options, groups: [] }

  const grouped = new Set()
  const groups = Object.entries(groupConfig)
    .map(([label, members]) => {
      const children = members.filter((v) => options.includes(v))
      children.forEach((v) => grouped.add(v))
      return { label, children }
    })
    .filter((g) => g.children.length > 0)

  const standalone = options.filter((v) => !grouped.has(v))
  return { standalone, groups }
}

function matchesArrayFacet(studyArray, selected) {
  if (!selected.length) return true
  const arr = studyArray || []
  return selected.some((v) => (v === NOT_RECORDED ? arr.length === 0 : arr.includes(v)))
}

// For one study, which of its own values were actually selected in the
// sidebar -- e.g. selecting "scRNA-seq" + "bulk RNA-seq" under Assay type
// (an OR match) still leaves it ambiguous, from the row alone, which of
// the two a given study actually has. Returns [{group, value}, ...], only
// for facet groups with an active selection.
export function matchedFacetValues(study, filters) {
  const tags = []
  for (const [key, field] of Object.entries(FACET_FIELDS)) {
    const selected = filters[key]
    if (!selected || !selected.length) continue
    const arr = study[field] || []
    if (arr.length === 0 && selected.includes(NOT_RECORDED)) {
      tags.push({ group: key, value: NOT_RECORDED })
      continue
    }
    for (const value of arr) {
      if (selected.includes(value)) tags.push({ group: key, value })
    }
  }
  return tags
}

export function filterStudies(studies, filters, query) {
  const q = query.trim().toLowerCase()
  return studies.filter((s) => {
    for (const [key, field] of Object.entries(FACET_FIELDS)) {
      if (!matchesArrayFacet(s[field], filters[key])) return false
    }
    if (!q) return true
    // Deliberately excludes s.notes: that's free-text provenance/curation
    // prose that often mentions OTHER studies' accessions in passing (e.g.
    // documenting why a related GSE was excluded or already held elsewhere)
    // -- including it made searching for one study's exact GSE number
    // return unrelated studies that merely reference it. Keep this to the
    // study's own identity fields.
    const haystack = [
      s.study_id,
      s.title,
      s.journal,
      ...(s.gse || []),
      s.bioproject,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
}
