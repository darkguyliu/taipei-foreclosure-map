import { AUCTION_COLORS } from '../constants'

export function PropertyCard({ property, isSelected, isFavorite, onSelect, onToggleFavorite }) {
  const color = AUCTION_COLORS[property.auction_count] || '#ff6b6b'
  return (
    <div
      className={`property-card ${isSelected ? 'selected' : ''}`}
      style={{ borderLeft: `3px solid ${color}` }}
      onClick={() => onSelect(property)}
    >
      <div className="property-card-address">{property.address}</div>
      <div className="property-card-meta">
        <span>底價 {(property.floor_price / 10000).toFixed(0)}萬</span>
        <span>第{property.auction_count}拍</span>
        <span>{property.auction_date}</span>
      </div>
      <div className="property-card-actions">
        <button
          className={`fav-btn ${isFavorite ? 'active' : ''}`}
          onClick={e => { e.stopPropagation(); onToggleFavorite(property.id) }}
        >
          {isFavorite ? '⭐' : '☆'} 收藏
        </button>
      </div>
    </div>
  )
}
