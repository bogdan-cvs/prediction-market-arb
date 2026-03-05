import { useState, useEffect, useCallback } from 'react'

const API = '/api'

export default function useArbitrage(wsSubscribe) {
  const [opportunities, setOpportunities] = useState([])
  const [platforms, setPlatforms] = useState({})
  const [mode, setMode] = useState({ dry_run: true })
  const [loading, setLoading] = useState(false)

  // Fetch opportunities
  const fetchOpportunities = useCallback(async () => {
    try {
      const res = await fetch(`${API}/arb/opportunities`)
      const data = await res.json()
      setOpportunities(data.opportunities || [])
    } catch {
      // backend not reachable
    }
  }, [])

  // Fetch platform status
  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch('/health')
      const data = await res.json()
      setPlatforms(data.platforms || {})
      setMode({ dry_run: data.dry_run })
    } catch {
      // backend not reachable
    }
  }, [])

  // Trigger scan
  const triggerScan = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${API}/arb/scan`, { method: 'POST' })
      const data = await res.json()
      setOpportunities(data.opportunities || [])
    } catch {
      // ignore
    }
    setLoading(false)
  }, [])

  // Execute opportunity
  const executeOpportunity = useCallback(async (opportunityId, quantity) => {
    try {
      const res = await fetch(`${API}/execution/execute`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          opportunity_id: opportunityId,
          quantity: quantity || null,
        }),
      })
      return await res.json()
    } catch (err) {
      return { success: false, error_message: err.message }
    }
  }, [])

  // Toggle mode
  const toggleMode = useCallback(async () => {
    try {
      const newMode = !mode.dry_run
      const res = await fetch(`${API}/execution/mode?dry_run=${newMode}`, {
        method: 'POST',
      })
      const data = await res.json()
      setMode({ dry_run: data.dry_run })
    } catch {
      // ignore
    }
  }, [mode.dry_run])

  // Subscribe to WS updates
  useEffect(() => {
    if (!wsSubscribe) return
    const unsub = wsSubscribe('opportunities', (data) => {
      if (Array.isArray(data)) {
        setOpportunities(data)
      }
    })
    return unsub
  }, [wsSubscribe])

  // Initial fetch
  useEffect(() => {
    fetchHealth()
    fetchOpportunities()
    const interval = setInterval(fetchHealth, 10000)
    return () => clearInterval(interval)
  }, [fetchHealth, fetchOpportunities])

  return {
    opportunities,
    platforms,
    mode,
    loading,
    triggerScan,
    executeOpportunity,
    toggleMode,
    fetchOpportunities,
  }
}
