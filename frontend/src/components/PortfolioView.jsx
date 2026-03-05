import { useState, useEffect } from 'react'
import { centsToDollars, platformLabel } from '../utils/formatting'

export default function PortfolioView() {
  const [summary, setSummary] = useState(null)

  useEffect(() => {
    const fetch_ = async () => {
      try {
        const res = await fetch('/api/portfolio/summary')
        setSummary(await res.json())
      } catch {
        // ignore
      }
    }
    fetch_()
    const interval = setInterval(fetch_, 15000)
    return () => clearInterval(interval)
  }, [])

  if (!summary) {
    return <div className="text-gray-500 text-sm">Loading portfolio...</div>
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-4 gap-3 text-sm">
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs">Total Balance</p>
          <p className="text-lg font-medium">{centsToDollars(summary.total_balance_cents)}</p>
        </div>
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs">Daily P&L</p>
          <p
            className={`text-lg font-medium ${
              summary.daily_pnl_cents >= 0 ? 'text-green-400' : 'text-red-400'
            }`}
          >
            {summary.daily_pnl_cents >= 0 ? '+' : ''}
            {centsToDollars(summary.daily_pnl_cents)}
          </p>
        </div>
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs">Exposure</p>
          <p className="text-lg font-medium">{centsToDollars(summary.total_exposure_cents)}</p>
        </div>
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs">Trades Today</p>
          <p className="text-lg font-medium">{summary.trade_count_today}</p>
        </div>
      </div>

      {summary.balances && summary.balances.length > 0 && (
        <div className="flex gap-2">
          {summary.balances.map((b) => (
            <div
              key={b.platform}
              className="text-xs bg-gray-900 rounded px-2 py-1 text-gray-400"
            >
              {platformLabel(b.platform)}: {centsToDollars(b.available_cents)}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
