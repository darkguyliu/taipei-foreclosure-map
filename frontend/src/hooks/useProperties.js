// frontend/src/hooks/useProperties.js
import { useState, useEffect } from 'react'

export function useProperties(district, filters = {}) {
  const [properties, setProperties] = useState([])
  const [lastRefreshedAt, setLastRefreshedAt] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!district) return
    setLoading(true)
    setError(null)
    setProperties([])
    const params = new URLSearchParams({ district })
    if (filters.minPrice != null) params.set('min_price', filters.minPrice)
    if (filters.maxPrice != null) params.set('max_price', filters.maxPrice)
    if (filters.auctionCount != null) params.set('auction_count', filters.auctionCount)
    if (filters.propertyType != null && filters.propertyType !== 'all')
      params.set('property_type', filters.propertyType)

    fetch(`/api/properties?${params}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => {
        setProperties(data.properties)
        setLastRefreshedAt(data.last_refreshed_at)
      })
      .catch(err => setError(`無法載入資料: ${err}`))
      .finally(() => setLoading(false))
  }, [district, filters.minPrice, filters.maxPrice, filters.auctionCount, filters.propertyType])

  return { properties, lastRefreshedAt, loading, error }
}
