// frontend/src/components/DistrictSelector.jsx
import { DISTRICT_GROUPS } from '../constants'

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
        {DISTRICT_GROUPS.map(group => (
          <optgroup key={group.city} label={group.city}>
            {group.districts.map(d => (
              <option key={d} value={d}>{d}</option>
            ))}
          </optgroup>
        ))}
      </select>
    </div>
  )
}
