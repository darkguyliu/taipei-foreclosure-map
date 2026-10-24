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
const DISTRICT_STORAGE_KEY = 'foreclosure_district'

const REFRESH_STATUS_MESSAGES = {
  400: '無效的行政區',
  409: '此行政區正在刷新中',
  429: '請求過於頻繁',
}

export default function App() {
  // Persisted so the post-refresh reload below doesn't drop the user back
  // onto the district picker with no selection — the reload is still a
  // full page load, but at least restores where they were.
  const [district, setDistrict] = useState(() => {
    try {
      return localStorage.getItem(DISTRICT_STORAGE_KEY) || ''
    } catch {
      return ''
    }
  })
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
  // Pending post-success reload timer, so it can be cancelled if the user
  // switches districts before it fires (see handleDistrictChange).
  const reloadTimerRef = useRef(null)
  // District with a /refresh request currently in flight, or null — so
  // switching away and back to it restores the disabled button instead
  // of re-enabling a click that would just come back as a 409.
  const pendingRequestDistrictRef = useRef(null)

  // Clear any stale throttle/error message from the previous district —
  // otherwise it lingers on screen after switching districts. Done in the
  // change handler itself rather than a useEffect on `district`, since an
  // effect that unconditionally calls setState on every change just
  // triggers an extra render for no benefit here.
  function handleDistrictChange(newDistrict) {
    districtRef.current = newDistrict
    setDistrict(newDistrict)
    try {
      localStorage.setItem(DISTRICT_STORAGE_KEY, newDistrict)
    } catch {
      // ignore — persistence is a nice-to-have, not required to function
    }
    setRefreshError('')
    setRefreshing(pendingRequestDistrictRef.current === newDistrict)
    if (reloadTimerRef.current) {
      clearTimeout(reloadTimerRef.current)
      reloadTimerRef.current = null
    }
  }

  async function handleRefresh() {
    if (!district || refreshing) return
    const requestedDistrict = district // snapshot — the user may switch away before this resolves
    pendingRequestDistrictRef.current = requestedDistrict
    setRefreshError('')
    setRefreshing(true)
    let resp
    try {
      resp = await fetch(`/api/refresh?district=${encodeURIComponent(requestedDistrict)}`, { method: 'POST' })
    } catch {
      if (pendingRequestDistrictRef.current === requestedDistrict) pendingRequestDistrictRef.current = null
      // Guard every bit of state this response touches against having
      // switched districts in the meantime — not just the error message,
      // or e.g. clearing `refreshing` here could re-enable the button for
      // a district whose own, still-in-flight request hasn't resolved.
      if (districtRef.current === requestedDistrict) {
        setRefreshError('刷新失敗，請檢查網路連線')
        setRefreshing(false)
      }
      return
    }
    if (!resp.ok) {
      // 429 (throttled) or 409 (already in progress) — don't reload, the
      // user needs to know nothing new was triggered.
      if (pendingRequestDistrictRef.current === requestedDistrict) pendingRequestDistrictRef.current = null
      if (districtRef.current === requestedDistrict) {
        const retryAfter = resp.headers.get('Retry-After')
        const message = REFRESH_STATUS_MESSAGES[resp.status] || '刷新失敗'
        setRefreshError(retryAfter ? `${message}（請 ${retryAfter} 秒後再試）` : message)
        setRefreshing(false)
      }
      return
    }
    if (pendingRequestDistrictRef.current === requestedDistrict) pendingRequestDistrictRef.current = null
    // Reload after a short delay to allow background task to complete.
    // Guarded the same way as the failure branches above: if the user
    // switched districts while this request was in flight,
    // handleDistrictChange already ran and had nothing to cancel yet
    // (this timer didn't exist until now) — scheduling it unconditionally
    // here would reload onto whatever district they switched to. Once
    // the timer *is* set, handleDistrictChange cancels it on any further
    // switch.
    if (districtRef.current === requestedDistrict) {
      reloadTimerRef.current = setTimeout(() => window.location.reload(), 3000)
    }
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
