import { useState } from 'react'

const GROUP_LABELS = {
  organism: 'Organism',
  assay_type: 'Assay type',
  disease_status: 'Disease status',
  tissue: 'Tissue',
  cell_type: 'Cell type',
  genotype: 'Genotype',
  primary_route: 'Primary route',
  journal: 'Journal',
}

// Collapsed by default -- landing on the page shows just the group headers
// (with a count of active selections), not every checkbox for every facet
// at once. Click a header to expand/collapse it.
const GROUP_ORDER = [
  'organism',
  'assay_type',
  'disease_status',
  'tissue',
  'cell_type',
  'genotype',
  'primary_route',
  'journal',
]

function FacetGroup({ groupKey, options, selected, onChange, expanded, onToggle }) {
  if (!options.length) return null
  const toggle = (opt) => {
    const next = selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt]
    onChange(next)
  }
  return (
    <div className="facet-group">
      <button
        type="button"
        className="facet-group-header"
        aria-expanded={expanded}
        onClick={() => onToggle(groupKey)}
      >
        <span className="facet-toggle-glyph">{expanded ? '–' : '+'}</span>
        <span className="facet-group-label">{GROUP_LABELS[groupKey] || groupKey}</span>
        {selected.length > 0 && <span className="facet-selected-count">{selected.length}</span>}
      </button>
      {expanded && (
        <div className="facet-options">
          {options.map((opt) => (
            <label key={String(opt)} className="facet-option">
              <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} />
              {String(opt)}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

export default function FilterSidebar({ facets, filters, onChange, onClearFilters, query, onQueryChange, resultCount }) {
  const [expandedGroups, setExpandedGroups] = useState({})
  const toggleGroup = (key) => setExpandedGroups((prev) => ({ ...prev, [key]: !prev[key] }))
  const set = (key) => (value) => onChange({ ...filters, [key]: value })
  const activeCount = GROUP_ORDER.reduce((sum, key) => sum + (filters[key]?.length || 0), 0)

  return (
    <aside className="filter-sidebar">
      <input
        className="search-box"
        type="search"
        placeholder="Search title, accession, notes..."
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
      />
      <div className="result-count-row">
        <span className="result-count">{resultCount} studies</span>
        <button
          type="button"
          className="clear-filters-button"
          onClick={onClearFilters}
          disabled={activeCount === 0}
        >
          Clear filters{activeCount > 0 ? ` (${activeCount})` : ''}
        </button>
      </div>

      {GROUP_ORDER.map((key) => (
        <FacetGroup
          key={key}
          groupKey={key}
          options={facets[key]}
          selected={filters[key]}
          onChange={set(key)}
          expanded={!!expandedGroups[key]}
          onToggle={toggleGroup}
        />
      ))}
    </aside>
  )
}
