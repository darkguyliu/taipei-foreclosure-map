import { Map, AdvancedMarker, InfoWindow, useMap } from '@vis.gl/react-google-maps'
import { useEffect } from 'react'
import { AUCTION_COLORS, DISTRICT_CENTERS } from '../constants'

const TAIPEI_CENTER = { lat: 25.0478, lng: 121.5319 }
const DISTRICT_ZOOM = 15

function hasCoords(p) {
  return p != null && p.lat != null && p.lng != null
}

function MarkerPin({ color, label }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      cursor: 'pointer',
    }}>
      <div style={{
        background: color,
        color: '#fff',
        fontWeight: 700,
        fontSize: 13,
        width: 32,
        height: 32,
        borderRadius: '50% 50% 50% 0',
        transform: 'rotate(-45deg)',
        border: '3px solid white',
        boxShadow: `0 2px 8px rgba(0,0,0,0.4), 0 0 12px ${color}80`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <span style={{ transform: 'rotate(45deg)' }}>{label}</span>
      </div>
    </div>
  )
}

export function MapView({ district, properties, selectedProperty, onSelectProperty, isFavorite, toggleFavorite, getAvgPrice }) {
  const map = useMap()

  // Center map on district change
  useEffect(() => {
    if (!map) return
    const center = DISTRICT_CENTERS[district]
    if (center) {
      map.panTo(center)
      map.setZoom(DISTRICT_ZOOM)
    } else {
      map.panTo(TAIPEI_CENTER)
      map.setZoom(13)
    }
  }, [district, map])

  // Pan to selected property (skip if geocoding never resolved coordinates)
  useEffect(() => {
    if (map && hasCoords(selectedProperty)) {
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
        {properties
          .filter(hasCoords)
          .map(p => (
            <AdvancedMarker
              key={p.id}
              position={{ lat: p.lat, lng: p.lng }}
              onClick={() => onSelectProperty(p)}
            >
              <MarkerPin
                color={AUCTION_COLORS[p.auction_count] || AUCTION_COLORS[3]}
                label={p.auction_count}
              />
            </AdvancedMarker>
          ))}

        {hasCoords(selectedProperty) && (
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
            🔗 公告文件
          </a>
        )}
      </div>
    </div>
  )
}
