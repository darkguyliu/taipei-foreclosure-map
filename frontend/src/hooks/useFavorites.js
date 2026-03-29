// frontend/src/hooks/useFavorites.js
import { useState, useEffect } from 'react'

const STORAGE_KEY = 'foreclosure_favorites'

export function useFavorites() {
  const [favoriteIds, setFavoriteIds] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]')
    } catch {
      return []
    }
  })

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favoriteIds))
  }, [favoriteIds])

  function toggleFavorite(id) {
    setFavoriteIds(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    )
  }

  function isFavorite(id) {
    return favoriteIds.includes(id)
  }

  return { favoriteIds, toggleFavorite, isFavorite }
}
