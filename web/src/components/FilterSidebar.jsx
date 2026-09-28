import { useEffect, useRef, useState } from 'react'
import { buildFacetTree } from '../facets.js'

const GROUP_LABELS = {
  organism: 'Organism',
  assay_type: 'Assay type',
  disease_status: 'Disease status',
  tissue: 'Tissue',
  cell_type: 'Cell type',
  genotype: 'Genotype',
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
]

// A checkbox that also supports the browser's native indeterminate visual
// state (a dash instead of a check) -- only settable via the DOM property,
// not a plain HTML attribute, hence the ref.
function TriStateCheckbox({ checked, indeterminate, onChange }) {
  const ref = useRef(null)
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = indeterminate
  }, [indeterminate])
  return <input ref={ref} type="checkbox" checked={checked} onChange={onChange} />
}

// One umbrella (e.g. "ALS") within a grouped facet -- its own checkbox
// selects/clears every child at once (indeterminate when some but not all
// children are selected), and an expand toggle reveals the children
// individually so a selection can be narrowed (e.g. ALS -> just "ALS
// (rapid progression)") without leaving the umbrella state ambiguous.
function FacetGroupUmbrella({ label, childValues, selected, onToggleChild, onToggleAll }) {
  const [expanded, setExpanded] = useState(false)
  const selectedChildren = childValues.filter((c) => selected.includes(c))
  const allSelected = selectedChildren.length === childValues.length
  const someSelected = selectedChildren.length > 0 && !allSelected

  return (
    <div className="facet-umbrella">
      <div className="facet-option facet-umbrella-row">
        <TriStateCheckbox
          checked={allSelected}
          indeterminate={someSelected}
          onChange={() => onToggleAll(childValues, !allSelected)}
        />
        <button
          type="button"
          className="facet-umbrella-label"
          onClick={() => setExpanded((v) => !v)}
        >
          <span className="facet-toggle-glyph facet-toggle-glyph-small">{expanded ? '–' : '+'}</span>
          {label}
          {selectedChildren.length > 0 && (
            <span className="facet-selected-count">{selectedChildren.length}</span>
          )}
        </button>
      </div>
      {expanded && (
        <div className="facet-umbrella-children">
          {childValues.map((child) => (
            <label key={child} className="facet-option">
              <input
                type="checkbox"
                checked={selected.includes(child)}
                onChange={() => onToggleChild(child)}
              />
              {child}
            </label>
          ))}
        </div>
      )}
    </div>
  )
}

function FacetGroup({ groupKey, options, selected, onChange, expanded, onToggle }) {
  if (!options.length) return null
  const toggle = (opt) => {
    const next = selected.includes(opt) ? selected.filter((v) => v !== opt) : [...selected, opt]
    onChange(next)
  }
  const toggleAll = (children, select) => {
    const withoutChildren = selected.filter((v) => !children.includes(v))
    onChange(select ? [...withoutChildren, ...children] : withoutChildren)
  }
  const { standalone, groups } = buildFacetTree(groupKey, options)

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
          {standalone.map((opt) => (
            <label key={String(opt)} className="facet-option">
              <input type="checkbox" checked={selected.includes(opt)} onChange={() => toggle(opt)} />
              {String(opt)}
            </label>
          ))}
          {groups.map(({ label, children }) => (
            <FacetGroupUmbrella
              key={label}
              label={label}
              childValues={children}
              selected={selected}
              onToggleChild={toggle}
              onToggleAll={toggleAll}
            />
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

      <a className="mcp-access-link" href="#mcp-access">See how to access MCP server</a>
    </aside>
  )
}
