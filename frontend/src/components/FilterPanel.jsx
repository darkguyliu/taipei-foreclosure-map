export function FilterPanel({ filters, onChange }) {
  function update(key, value) {
    onChange({ ...filters, [key]: value || undefined })
  }

  return (
    <div className="filter-panel">
      <div className="filter-row">
        <label>底價下限（萬）</label>
        <input
          type="number"
          min="0"
          placeholder="不限"
          value={filters.minPrice ? filters.minPrice / 10000 : ''}
          onChange={e => update('minPrice', e.target.value ? Number(e.target.value) * 10000 : null)}
        />
      </div>
      <div className="filter-row">
        <label>底價上限（萬）</label>
        <input
          type="number"
          min="0"
          placeholder="不限"
          value={filters.maxPrice ? filters.maxPrice / 10000 : ''}
          onChange={e => update('maxPrice', e.target.value ? Number(e.target.value) * 10000 : null)}
        />
      </div>
      <div className="filter-row">
        <label>拍次</label>
        <select value={filters.auctionCount || 'all'} onChange={e => update('auctionCount', e.target.value === 'all' ? null : Number(e.target.value))}>
          <option value="all">全部</option>
          <option value="1">第1拍</option>
          <option value="2">第2拍</option>
          <option value="3">第3拍以上</option>
        </select>
      </div>
      <div className="filter-row">
        <label>類型</label>
        <select value={filters.propertyType || 'all'} onChange={e => update('propertyType', e.target.value === 'all' ? null : e.target.value)}>
          <option value="all">全部</option>
          <option value="住宅">住宅</option>
          <option value="商辦">商辦</option>
          <option value="土地">土地</option>
          <option value="其他">其他</option>
        </select>
      </div>
    </div>
  )
}
