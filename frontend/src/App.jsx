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

export default function App() {
  const [district, setDistrict] = useState('')
  const [filters, setFilters] = useState({})
  const [selectedProperty, setSelectedProperty] = useState(null)
  const [activeTab, setActiveTab] = useState('all') // 'all' | 'favorites'

  const { properties, lastRefreshedAt, loading, error } = useProperties(district, filters)
  const { getAvgPrice } = useAvgPrices(district)
  const { favoriteIds, toggleFavorite, isFavorite } = useFavorites()

  async function handleRefresh() {
    if (!district) return
    await fetch(`/api/refresh?district=${encodeURIComponent(district)}`, { method: 'POST' })
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
          <DistrictSelector selected={district} onChange={setDistrict} />
          {district && (
            <button className="refresh-btn" onClick={handleRefresh}>
              🔄 刷新資料
            </button>
          )}
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
