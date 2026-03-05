import { useState, useEffect } from 'react'
import { platformLabel } from '../utils/formatting'

export default function MarketMatcher() {
  const [matches, setMatches] = useState([])
  const [loading, setLoading] = useState(false)

  const fetchMatches = async () => {
    try {
      const res = await fetch('/api/markets/matches')
      const data = await res.json()
      setMatches(data.matches || [])
    } catch {
      // ignore
    }
  }

  const refreshMatches = async () => {
    setLoading(true)
    try {
      await fetch('/api/markets/matches/refresh', { method: 'POST' })
      await fetchMatches()
    } catch {
      // ignore
    }
    setLoading(false)
  }

  const verifyMatch = async (matchId, verified) => {
    await fetch(`/api/markets/matches/${matchId}/verify?verified=${verified}`, {
      method: 'POST',
    })
    await fetchMatches()
  }

  useEffect(() => {
    fetchMatches()
  }, [])

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-200">Market Matches ({matches.length})</h3>
        <button
          className="px-3 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 transition-colors"
          onClick={refreshMatches}
          disabled={loading}
        >
          {loading ? 'Refreshing...' : 'Refresh Matches'}
        </button>
      </div>

      <div className="space-y-2 max-h-80 overflow-y-auto">
        {matches.map((match) => (
          <div
            key={match.match_id}
            className={`bg-gray-900 rounded p-3 text-sm border ${
              match.verified ? 'border-green-800' : 'border-gray-800'
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-500">
                Score: {(match.match_score * 100).toFixed(0)}%
              </span>
              <div className="flex gap-1">
                {!match.verified && (
                  <button
                    className="px-2 py-0.5 text-xs rounded bg-green-900 hover:bg-green-800 text-green-300"
                    onClick={() => verifyMatch(match.match_id, true)}
                  >
                    Verify
                  </button>
                )}
                <button
                  className="px-2 py-0.5 text-xs rounded bg-red-900 hover:bg-red-800 text-red-300"
                  onClick={() => verifyMatch(match.match_id, false)}
                >
                  Reject
                </button>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-2">
              {Object.entries(match.platforms || {}).map(([plat, info]) => (
                <div key={plat} className="text-xs">
                  <span className="text-gray-400">{platformLabel(plat)}:</span>{' '}
                  <span className="text-gray-300 truncate block" title={info.title}>
                    {info.title}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
