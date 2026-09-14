// Facet options are always derived from whatever distinct values actually
// appear in the fetched catalog -- never a hardcoded taxonomy -- so the
// browser can't drift out of sync as new studies/values get added. See
// DESIGN.md's "Web app: filters/facets" section.

function distinct(values) {
  return Array.from(new Set(values.filter((v) => v !== null && v !== undefined && v !== ''))).sort()
}

export function buildStudyFacets(studies) {
  return {
    organism: distinct(studies.flatMap((s) => s.organisms || [])),
    assay_type: distinct(studies.flatMap((s) => s.assay_types || [])),
    // disease_status/tissue filter on the collection's canonical vocabulary
    // (disease_statuses_canonical/tissues_canonical -- deduped centrally on
    // HTCF, see DESIGN.md) rather than the raw disease_statuses/tissues
    // values, which still carry every spelling variant a source study used.
    // The raw values aren't dropped -- they still display per-sample in
    // StudyDetail -- this only changes what powers the sidebar checkboxes.
    disease_status: distinct(studies.flatMap((s) => s.disease_statuses_canonical || [])),
    tissue: distinct(studies.flatMap((s) => s.tissues_canonical || [])),
    cell_type: distinct(studies.flatMap((s) => s.cell_types || [])),
    genotype: distinct(studies.flatMap((s) => s.genotypes_canonical || [])),
    primary_route: distinct(studies.map((s) => s.primary_route)),
    journal: distinct(studies.map((s) => s.journal)),
  }
}

function matchesArrayFacet(studyArray, selected) {
  if (!selected.length) return true
  return (studyArray || []).some((v) => selected.includes(v))
}

function matchesScalarFacet(value, selected) {
  if (!selected.length) return true
  return selected.includes(value)
}

export function filterStudies(studies, filters, query) {
  const q = query.trim().toLowerCase()
  return studies.filter((s) => {
    if (!matchesArrayFacet(s.organisms, filters.organism)) return false
    if (!matchesArrayFacet(s.assay_types, filters.assay_type)) return false
    if (!matchesArrayFacet(s.disease_statuses_canonical, filters.disease_status)) return false
    if (!matchesArrayFacet(s.tissues_canonical, filters.tissue)) return false
    if (!matchesArrayFacet(s.cell_types, filters.cell_type)) return false
    if (!matchesArrayFacet(s.genotypes_canonical, filters.genotype)) return false
    if (!matchesScalarFacet(s.primary_route, filters.primary_route)) return false
    if (!matchesScalarFacet(s.journal, filters.journal)) return false
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
