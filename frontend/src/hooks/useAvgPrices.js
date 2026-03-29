// frontend/src/hooks/useAvgPrices.js
import { useState, useEffect } from 'react'

export function useAvgPrices(district) {
  const [avgPrices, setAvgPrices] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!district) return
    setLoading(true)
    fetch(`/api/avg-prices?district=${encodeURIComponent(district)}`)
      .then(r => r.ok ? r.json() : Promise.reject(r.status))
      .then(data => setAvgPrices(data.avg_prices))
      .catch(() => setAvgPrices([]))
      .finally(() => setLoading(false))
  }, [district])

  // Returns avg price in 萬/坪 for a given property_type
  function getAvgPrice(propertyType) {
    const entry = avgPrices.find(p => p.property_type === propertyType)
    return entry ? entry.avg_price : null
  }

  return { avgPrices, loading, getAvgPrice }
}
