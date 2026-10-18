// frontend/src/App.jsx
import { useState, useEffect, useRef } from 'react'
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
  const [refreshing, setRefreshing] = useState(false)

  const { properties, lastRefreshedAt, loading, error } = useProperties(district, filters)
  const { getAvgPrice } = useAvgPrices(district)
  const { favoriteIds, toggleFavorite, isFavorite } = useFavorites()

  // `district` inside handleRefresh's closure is the value from the render
  // that created it — it never changes after an await, so comparing
  // against it directly is always true. This ref always holds the latest
  // value instead, independent of which render's closure is still
  // running. Updated only in the event handler below (never during
  // render) since district only ever changes through it.
  const districtRef = useRef(district)

  // Clear any stale throttle/error message from the previous district —
  // otherwise it lingers on screen after switching districts. Done in the
  // change handler itself rather than a useEffect on `district`, since an
  // effect that unconditionally calls setState on every change just
  // triggers an extra render for no benefit here.
  function handleDistrictChange(newDistrict) {
    districtRef.current = newDistrict
    setDistrict(newDistrict)
    setRefreshError('')
    setRefreshing(false)
  }

  async function handleRefresh() {
    if (!district || refreshing) return
    const requestedDistrict = district // snapshot — the user may switch away before this resolves
    setRefreshError('')
    setRefreshing(true)
    let resp
    try {
      resp = await fetch(`/api/refresh?district=${encodeURIComponent(requestedDistrict)}`, { method: 'POST' })
    } catch {
      if (districtRef.current === requestedDistrict) setRefreshError('刷新失敗，請檢查網路連線')
      setRefreshing(false)
      return
    }
    if (!resp.ok) {
      // 429 (throttled) or 409 (already in progress) — don't reload, the
      // user needs to know nothing new was triggered. Only show this if
      // they're still looking at the district it's actually about —
      // otherwise a slow response for a district they've since left
      // would show up as an error on whatever they switched to instead.
      if (districtRef.current === requestedDistrict) {
        const retryAfter = resp.headers.get('Retry-After')
        const message = REFRESH_STATUS_MESSAGES[resp.status] || '刷新失敗'
        setRefreshError(retryAfter ? `${message}（請 ${retryAfter} 秒後再試）` : message)
      }
      setRefreshing(false)
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
            <button className="refresh-btn" onClick={handleRefresh} disabled={refreshing}>
              {refreshing ? '⏳ 刷新中...' : '🔄 刷新資料'}
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
