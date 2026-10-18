// frontend/src/App.jsx
import { useState, useEffect } from 'react'
import { APIProvider } from '@vis.gl/react-google-maps'
import { DistrictSelector } from './components/DistrictSelector'
import { Sidebar } from './components/Sidebar'
import { MapView } from './components/MapView'
import { useProperties } from './hooks/useProperties'
import { useAvgPrices } from './hooks/useAvgPrices'
import { useFavorites } from './hooks/useFavorites'
import './App.css'

const MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ''

const REFRESH_STATUS_MESSAGES = {
  400: '無效的行政區',
  409: '此行政區正在刷新中',
  429: '請求過於頻繁',
}

export default function App() {
  const [district, setDistrict] = useState('')
  const [filters, setFilters] = useState({})
  const [selectedProperty, setSelectedProperty] = useState(null)
  const [activeTab, setActiveTab] = useState('all') // 'all' | 'favorites'
  const [refreshError, setRefreshError] = useState('')

  const { properties, lastRefreshedAt, loading, error } = useProperties(district, filters)
  const { getAvgPrice } = useAvgPrices(district)
  const { favoriteIds, toggleFavorite, isFavorite } = useFavorites()

  // Clear any stale throttle/error message from the previous district —
  // otherwise it lingers on screen after switching districts. Done in the
  // change handler itself rather than a useEffect on `district`, since an
  // effect that unconditionally calls setState on every change just
  // triggers an extra render for no benefit here.
  function handleDistrictChange(newDistrict) {
    setDistrict(newDistrict)
    setRefreshError('')
  }

  async function handleRefresh() {
    if (!district) return
    setRefreshError('')
    let resp
    try {
      resp = await fetch(`/api/refresh?district=${encodeURIComponent(district)}`, { method: 'POST' })
    } catch {
      setRefreshError('刷新失敗，請檢查網路連線')
      return
    }
    if (!resp.ok) {
      // 429 (throttled) or 409 (already in progress) — don't reload, the
      // user needs to know nothing new was triggered.
      const retryAfter = resp.headers.get('Retry-After')
      const message = REFRESH_STATUS_MESSAGES[resp.status] || '刷新失敗'
      setRefreshError(retryAfter ? `${message}（請 ${retryAfter} 秒後再試）` : message)
      return
    }
    // Reload after a short delay to allow background task to complete
    setTimeout(() => window.location.reload(), 3000)
  }

  const displayProperties = activeTab === 'favorites'
    ? properties.filter(p => favoriteIds.includes(p.id))
    : properties

  // Fetch any favorited properties not in the current district's loaded data
  const [crossDistrictFavs, setCrossDistrictFavs] = useState([])
  useEffect(() => {
    if (activeTab !== 'favorites') return
    const missingIds = favoriteIds.filter(id => !properties.some(p => p.id === id))
    Promise.all(missingIds.map(id =>
      fetch(`/api/properties/${id}`).then(r => r.ok ? r.json() : null)
    )).then(results => setCrossDistrictFavs(results.filter(Boolean)))
  }, [activeTab, favoriteIds, properties])

  const favoritesDisplay = activeTab === 'favorites'
    ? [...displayProperties, ...crossDistrictFavs.filter(p => !displayProperties.some(d => d.id === p.id))]
    : displayProperties

  return (
    <APIProvider apiKey={MAPS_API_KEY}>
      <div className="app-layout">
        <header className="app-header">
          <span className="app-title">🏠 雙北法拍屋地圖</span>
          <DistrictSelector selected={district} onChange={handleDistrictChange} />
          {district && (
            <button className="refresh-btn" onClick={handleRefresh}>
              🔄 刷新資料
            </button>
          )}
          {refreshError && <span className="refresh-error">{refreshError}</span>}
        </header>
        <div className="app-body">
          <Sidebar
            properties={activeTab === 'favorites' ? favoritesDisplay : displayProperties}
            totalCount={properties.length}
            loading={loading}
            error={error}
            lastRefreshedAt={lastRefreshedAt}
            filters={filters}
            onFiltersChange={setFilters}
            selectedProperty={selectedProperty}
            onSelectProperty={setSelectedProperty}
            activeTab={activeTab}
            onTabChange={setActiveTab}
            isFavorite={isFavorite}
            toggleFavorite={toggleFavorite}
            getAvgPrice={getAvgPrice}
          />
          <MapView
            district={district}
            properties={properties}
            selectedProperty={selectedProperty}
            onSelectProperty={setSelectedProperty}
            isFavorite={isFavorite}
            toggleFavorite={toggleFavorite}
            getAvgPrice={getAvgPrice}
          />
        </div>
      </div>
    </APIProvider>
  )
}
