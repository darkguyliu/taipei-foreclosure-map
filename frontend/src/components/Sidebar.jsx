import { FilterPanel } from './FilterPanel'
import { PropertyCard } from './PropertyCard'

export function Sidebar({
  properties, totalCount, loading, error, lastRefreshedAt,
  filters, onFiltersChange,
  selectedProperty, onSelectProperty,
  activeTab, onTabChange,
  isFavorite, toggleFavorite,
  getAvgPrice,
}) {
  const residentialAvg = getAvgPrice('住宅')

  return (
    <aside className="sidebar">
      <FilterPanel filters={filters} onChange={onFiltersChange} />

      {residentialAvg && (
        <div className="avg-price-banner">
          💰 住宅均價 <strong>{residentialAvg} 萬/坪</strong>
          {lastRefreshedAt && (
            <span className="refreshed-at">
              更新於 {new Date(lastRefreshedAt).toLocaleString('zh-TW', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
        </div>
      )}

      <div className="tab-bar">
        <button className={activeTab === 'all' ? 'active' : ''} onClick={() => onTabChange('all')}>
          全部 ({totalCount})
        </button>
        <button className={activeTab === 'favorites' ? 'active' : ''} onClick={() => onTabChange('favorites')}>
          收藏
        </button>
      </div>

      <div className="property-list">
        {loading && <p className="list-msg">載入中...</p>}
        {error && <p className="list-msg error">{error}</p>}
        {!loading && !error && properties.length === 0 && (
          <p className="list-msg">
            {activeTab === 'favorites' ? '尚無收藏物件' : '尚無資料，請點擊「刷新資料」'}
          </p>
        )}
        {properties.map(p => (
          <PropertyCard
            key={p.id}
            property={p}
            isSelected={selectedProperty?.id === p.id}
            isFavorite={isFavorite(p.id)}
            onSelect={onSelectProperty}
            onToggleFavorite={toggleFavorite}
          />
        ))}
      </div>
    </aside>
  )
}
