import { Map, AdvancedMarker, InfoWindow, useMap } from '@vis.gl/react-google-maps'
import { useEffect } from 'react'

const TAIPEI_CENTER = { lat: 25.0478, lng: 121.5319 }
const AUCTION_COLORS = { 1: '#4a8fd4', 2: '#f4a430', 3: '#ff6b6b' }

function MarkerPin({ color }) {
  return (
    <div style={{
      width: 16, height: 16,
      background: color,
      borderRadius: '50% 50% 50% 0',
      transform: 'rotate(-45deg)',
      border: '2px solid white',
      boxShadow: `0 0 6px ${color}`,
    }} />
  )
}

export function MapView({ properties, selectedProperty, onSelectProperty, isFavorite, toggleFavorite, getAvgPrice }) {
  const map = useMap()

  useEffect(() => {
    if (selectedProperty && map) {
      map.panTo({ lat: selectedProperty.lat, lng: selectedProperty.lng })
    }
  }, [selectedProperty, map])

  return (
    <div className="map-container">
      <Map
        defaultCenter={TAIPEI_CENTER}
        defaultZoom={13}
        mapId="foreclosure-map"
        gestureHandling="greedy"
        disableDefaultUI={false}
      >
        {properties.map(p => (
          <AdvancedMarker
            key={p.id}
            position={{ lat: p.lat, lng: p.lng }}
            onClick={() => onSelectProperty(p)}
          >
            <MarkerPin color={AUCTION_COLORS[p.auction_count] || '#ff6b6b'} />
          </AdvancedMarker>
        ))}

        {selectedProperty && (
          <InfoWindow
            position={{ lat: selectedProperty.lat, lng: selectedProperty.lng }}
            onCloseClick={() => onSelectProperty(null)}
          >
            <PropertyInfoWindow
              property={selectedProperty}
              isFavorite={isFavorite(selectedProperty.id)}
              onToggleFavorite={() => toggleFavorite(selectedProperty.id)}
              getAvgPrice={getAvgPrice}
            />
          </InfoWindow>
        )}
      </Map>
    </div>
  )
}

function PropertyInfoWindow({ property, isFavorite, onToggleFavorite, getAvgPrice }) {
  const pricePerPing = property.area > 0
    ? ((property.floor_price / 10000) / property.area).toFixed(1)
    : null
  const avgPrice = getAvgPrice(property.property_type)
  const discount = avgPrice && pricePerPing
    ? Math.round((1 - Number(pricePerPing) / avgPrice) * 100)
    : null

  return (
    <div className="info-window">
      <div className="iw-address">{property.address}</div>
      <table className="iw-table">
        <tbody>
          <tr><td>底價</td><td><strong>{(property.floor_price / 10000).toFixed(0)} 萬</strong></td></tr>
          <tr><td>面積</td><td>{property.area} 坪</td></tr>
          <tr><td>類型</td><td>{property.property_type}</td></tr>
          <tr><td>拍次</td><td>第 {property.auction_count} 拍</td></tr>
          <tr><td>拍賣日</td><td>{property.auction_date}</td></tr>
          <tr><td>法院</td><td>{property.court}</td></tr>
          {pricePerPing && <tr><td>底價/坪</td><td>{pricePerPing} 萬</td></tr>}
          {avgPrice && <tr><td>區域均價</td><td>{avgPrice} 萬/坪</td></tr>}
          <tr><td>折扣</td><td style={{ color: discount !== null ? (discount > 0 ? '#7cff7c' : '#ff6b6b') : '#999' }}>
            {discount === null
              ? '載入中...'
              : discount > 0 ? `低於均價 ${discount}%` : `高於均價 ${-discount}%`}
          </td></tr>
        </tbody>
      </table>
      <div className="iw-actions">
        <button onClick={onToggleFavorite} className={isFavorite ? 'active' : ''}>
          {isFavorite ? '⭐ 已收藏' : '☆ 收藏'}
        </button>
        {property.auction_url && (
          <a href={property.auction_url} target="_blank" rel="noreferrer">
            🔗 司法院公告
          </a>
        )}
      </div>
    </div>
  )
}
