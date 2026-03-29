// frontend/src/components/DistrictSelector.jsx
import { TAIPEI_DISTRICTS } from '../constants'

export function DistrictSelector({ selected, onChange }) {
  return (
    <div className="district-selector">
      <label htmlFor="district-select">選擇區域</label>
      <select
        id="district-select"
        value={selected}
        onChange={e => onChange(e.target.value)}
      >
        <option value="">-- 請選擇 --</option>
        {TAIPEI_DISTRICTS.map(d => (
          <option key={d} value={d}>{d}</option>
        ))}
      </select>
    </div>
  )
}
