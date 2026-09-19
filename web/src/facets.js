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
    const haystack = [
      s.study_id,
      s.title,
      s.journal,
      s.notes,
      ...(s.gse || []),
      s.bioproject,
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase()
    return haystack.includes(q)
  })
}
