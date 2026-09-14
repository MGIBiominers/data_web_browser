import { distinctFormats, formatLabel } from '../format.js'

function formatBytes(bytes) {
  if (bytes == null) return ''
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let n = bytes
  let i = 0
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${n.toFixed(1)} ${units[i]}`
}

export default function StudyDetail({ study, samples, onClose }) {
  if (!study) return null
  const studySamples = samples.filter((s) => s.study_id === study.study_id)
  const dataFiles = (study.processed_files || []).filter((f) => f.category === 'data')
  const formats = distinctFormats(study.processed_files)
  const catalogNumber = (study.gse || [])[0] || study.bioproject || study.cellxgene_collection || study.synapse || study.study_id
  // Accessions already shown as the catalog-number tag above shouldn't repeat
  // in the accessions line below -- e.g. a single-GSE study would otherwise
  // show "GSE283507" twice.
  const remainingGse = (study.gse || []).filter((g) => g !== catalogNumber)

  return (
    <div className="study-detail-overlay" onClick={onClose}>
      <div className="study-detail" onClick={(e) => e.stopPropagation()}>
        <button className="close-button" onClick={onClose}>×</button>
        <h2>{study.title || study.study_id}</h2>
        <div className="study-meta">
          <span className="catalog-number">{catalogNumber}</span>
          <span>{study.journal} {study.year ? `(${study.year})` : ''}</span>
          {study.doi && <a href={`https://doi.org/${study.doi}`} target="_blank" rel="noreferrer">DOI</a>}
        </div>

        <div className="format-badges">
          {formats.length > 0 ? (
            formats.map((f) => (
              <span key={f} className="format-badge">{f}</span>
            ))
          ) : (
            <span className="format-badge format-badge-none">not yet processed</span>
          )}
        </div>

        {study.summary && <p className="study-summary">{study.summary}</p>}

        <div className="study-accessions">
          {study.bioproject && study.bioproject !== catalogNumber && <span>BioProject: {study.bioproject}</span>}
          {remainingGse.length > 0 && <span>Also: {remainingGse.join(', ')}</span>}
          {study.cellxgene_collection && study.cellxgene_collection !== catalogNumber && <span>CELLxGENE: {study.cellxgene_collection}</span>}
          {study.synapse && study.synapse !== catalogNumber && <span>Synapse: {study.synapse}</span>}
        </div>

        {study.notes && <p className="study-notes">{study.notes}</p>}

        <h3>Processed data files ({dataFiles.length})</h3>
        <table className="file-table">
          <thead>
            <tr><th>Name</th><th>Format</th><th>Size</th></tr>
          </thead>
          <tbody>
            {dataFiles.map((f) => (
              <tr key={f.name}>
                <td>{f.name}</td>
                <td>{formatLabel(f.name)}</td>
                <td>{formatBytes(f.bytes)}</td>
              </tr>
            ))}
            {dataFiles.length === 0 && (
              <tr><td colSpan={3} className="empty-row">No processed data files yet — only raw sequencing data exists for this study so far.</td></tr>
            )}
          </tbody>
        </table>

        <h3>Samples ({studySamples.length})</h3>
        <div className="sample-table-wrap">
          <table className="sample-table">
            <thead>
              <tr>
                <th>Sample</th><th>Disease</th><th>Tissue</th><th>Genotype</th><th>Sex</th><th>Treatment</th><th>Platform</th>
              </tr>
            </thead>
            <tbody>
              {studySamples.slice(0, 200).map((s) => (
                <tr key={s.sample_id || s.accession}>
                  <td>{s.sample_id || s.accession}</td>
                  <td>{s.disease_status}</td>
                  <td>{s.tissue_or_cell_type}</td>
                  <td>{s.genotype}</td>
                  <td>{s.sex}</td>
                  <td>{s.treatment}</td>
                  <td>{s.platform}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {studySamples.length > 200 && (
            <div className="sample-table-truncated">Showing first 200 of {studySamples.length} samples.</div>
          )}
        </div>
      </div>
    </div>
  )
}
