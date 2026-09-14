import { distinctFormats } from '../format.js'

export default function StudyTable({ studies, onSelect }) {
  return (
    <table className="study-table">
      <thead>
        <tr>
          <th>Study</th>
          <th>Organism</th>
          <th>Assay</th>
          <th>Samples</th>
          <th>Data format</th>
        </tr>
      </thead>
      <tbody>
        {studies.map((s) => {
          const formats = distinctFormats(s.processed_files)
          return (
            <tr key={s.study_id} onClick={() => onSelect(s.study_id)} className="study-row">
              <td>
                <div className="study-title">{s.title || s.study_id}</div>
                <div className="study-id">{s.study_id}</div>
              </td>
              <td>{(s.organisms || []).join(', ')}</td>
              <td>{(s.assay_types || []).join(', ')}</td>
              <td className="samples-count">{s.n_samples}</td>
              <td>
                {formats.length > 0 ? (
                  formats.join(', ')
                ) : (
                  <span className="not-processed">not yet processed</span>
                )}
              </td>
            </tr>
          )
        })}
        {studies.length === 0 && (
          <tr>
            <td colSpan={5} className="empty-row">No studies match the current filters.</td>
          </tr>
        )}
      </tbody>
    </table>
  )
}
