import { useState, useEffect } from 'react'
import { centsToDollars, timeAgo, platformLabel } from '../utils/formatting'

export default function ProfitTracker() {
  const [trades, setTrades] = useState([])

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await fetch('/api/execution/history?limit=20')
        const data = await res.json()
        setTrades(data.trades || [])
      } catch {
        // ignore
      }
    }
    fetch_()
    const interval = setInterval(fetch_, 10000)
    return () => clearInterval(interval)
  }, [])

  const totalProfit = trades.reduce((sum, t) => sum + (t.net_profit_cents || 0), 0)

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="font-medium text-gray-200">Trade History</h3>
        <span
          className={`text-sm font-medium ${
            totalProfit >= 0 ? 'text-green-400' : 'text-red-400'
          }`}
        >
          Total: {totalProfit >= 0 ? '+' : ''}{centsToDollars(totalProfit)}
        </span>
      </div>

      {trades.length === 0 ? (
        <p className="text-gray-500 text-sm">No trades yet</p>
      ) : (
        <div className="space-y-1 max-h-60 overflow-y-auto">
          {trades.map((t) => (
            <div
              key={t.id}
              className="flex items-center justify-between bg-gray-900 rounded px-3 py-2 text-sm"
            >
              <div className="flex items-center gap-2">
                {t.dry_run ? (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-yellow-900 text-yellow-300">
                    DRY
                  </span>
                ) : (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-green-900 text-green-300">
                    LIVE
                  </span>
                )}
                <span className="text-gray-400">
                  {platformLabel(t.platform_a)} / {platformLabel(t.platform_b)}
                </span>
              </div>
              <div className="flex items-center gap-3">
                <span className="text-gray-400">x{t.quantity}</span>
                <span
                  className={`font-medium ${
                    t.net_profit_cents >= 0 ? 'text-green-400' : 'text-red-400'
                  }`}
                >
                  {t.net_profit_cents >= 0 ? '+' : ''}
                  {centsToDollars(t.net_profit_cents)}
                </span>
                <span className="text-gray-600 text-xs">{timeAgo(t.executed_at)}</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
