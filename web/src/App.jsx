import { useEffect, useMemo, useState } from 'react'
import { fetchCatalog, fetchSamples } from './api.js'
import { buildStudyFacets, filterStudies } from './facets.js'
import FilterSidebar from './components/FilterSidebar.jsx'
import StudyTable from './components/StudyTable.jsx'
import StudyDetail from './components/StudyDetail.jsx'

const EMPTY_FILTERS = {
  organism: [],
  assay_type: [],
  disease_status: [],
  tissue: [],
  cell_type: [],
  genotype: [],
  primary_route: [],
  journal: [],
}

export default function App() {
  const [catalog, setCatalog] = useState(null)
  const [samples, setSamples] = useState([])
  const [error, setError] = useState(null)
  const [query, setQuery] = useState('')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [selectedId, setSelectedId] = useState(null)

  useEffect(() => {
    Promise.all([fetchCatalog(), fetchSamples()])
      .then(([catalogDoc, samplesDoc]) => {
        setCatalog(catalogDoc)
        setSamples(samplesDoc.samples || [])
      })
      .catch((err) => setError(err.message))
  }, [])

  const studies = catalog?.studies || []
  const facets = useMemo(() => buildStudyFacets(studies), [studies])
  const filtered = useMemo(() => filterStudies(studies, filters, query), [studies, filters, query])
  const selected = useMemo(
    () => studies.find((s) => s.study_id === selectedId) || null,
    [studies, selectedId],
  )

  if (error) {
    return (
      <div className="error-banner">
        Failed to load dataset catalog: {error}
        <br />
        (Set VITE_METADATA_BASE_URL to point at your CloudFront/S3 metadata prefix.)
      </div>
    )
  }

  if (!catalog) {
    return <div className="loading">Loading catalog…</div>
  }

  return (
    <div className="app">
      <header className="app-header">
        <h1>ALS Dataset Browser</h1>
        <span className="catalog-meta">
          <strong>{studies.length} studies</strong>
          catalog built {new Date(catalog.generated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}
        </span>
      </header>
      <div className="app-body">
        <FilterSidebar
          facets={facets}
          filters={filters}
          onChange={setFilters}
          onClearFilters={() => setFilters(EMPTY_FILTERS)}
          query={query}
          onQueryChange={setQuery}
          resultCount={filtered.length}
        />
        <main className="app-main">
          <StudyTable studies={filtered} onSelect={setSelectedId} />
        </main>
      </div>
      <StudyDetail study={selected} samples={samples} onClose={() => setSelectedId(null)} />
    </div>
  )
}
