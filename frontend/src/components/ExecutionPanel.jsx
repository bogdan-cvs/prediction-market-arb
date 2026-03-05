import { useState } from 'react'
import { centsToPrice, centsToDollars, platformLabel, profitColor } from '../utils/formatting'

export default function ExecutionPanel({ opportunity, onExecute, dryRun }) {
  const [quantity, setQuantity] = useState('')
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState(null)

  if (!opportunity) {
    return (
      <div className="flex items-center justify-center h-full text-gray-500">
        <p>Select an opportunity to trade</p>
      </div>
    )
  }

  const opp = opportunity
  const qty = parseInt(quantity) || opp.max_quantity
  const estProfit = (opp.net_profit_cents * qty / 100).toFixed(2)

  const handleExecute = async () => {
    setExecuting(true)
    setResult(null)
    const res = await onExecute(opp.opportunity_id, qty)
    setResult(res)
    setExecuting(false)
  }

  return (
    <div className="space-y-4">
      <h3 className="font-medium text-gray-200 truncate" title={opp.market_title}>
        {opp.market_title}
      </h3>

      <div className="grid grid-cols-2 gap-3 text-sm">
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs mb-1">LEG A</p>
          <p className="font-medium">{platformLabel(opp.leg_a?.platform)}</p>
          <p className="text-gray-300">
            Buy {opp.leg_a?.side} @ {centsToPrice(opp.leg_a?.price_cents)}
          </p>
          <p className="text-gray-500 text-xs">Avail: {opp.leg_a?.available_qty}</p>
        </div>
        <div className="bg-gray-900 rounded p-3">
          <p className="text-gray-400 text-xs mb-1">LEG B</p>
          <p className="font-medium">{platformLabel(opp.leg_b?.platform)}</p>
          <p className="text-gray-300">
            Buy {opp.leg_b?.side} @ {centsToPrice(opp.leg_b?.price_cents)}
          </p>
          <p className="text-gray-500 text-xs">Avail: {opp.leg_b?.available_qty}</p>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 text-sm text-center">
        <div>
          <p className="text-gray-400 text-xs">Cost</p>
          <p>{centsToPrice(opp.total_cost_cents)}</p>
        </div>
        <div>
          <p className="text-gray-400 text-xs">Net Profit</p>
          <p className={profitColor(opp.net_profit_cents)}>
            {centsToPrice(opp.net_profit_cents)}
          </p>
        </div>
        <div>
          <p className="text-gray-400 text-xs">ROI</p>
          <p className="text-green-400">{opp.net_profit_pct}%</p>
        </div>
      </div>

      <div>
        <label className="block text-xs text-gray-400 mb-1">Quantity</label>
        <input
          type="number"
          className="w-full bg-gray-900 border border-gray-700 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
          placeholder={`Max: ${opp.max_quantity}`}
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          min={1}
          max={opp.max_quantity}
        />
        <p className="text-xs text-gray-500 mt-1">
          Est. profit: <span className="text-green-400">${estProfit}</span>
        </p>
      </div>

      <button
        className={`w-full py-2.5 rounded font-medium text-sm transition-colors ${
          dryRun
            ? 'bg-yellow-600 hover:bg-yellow-500 text-black'
            : 'bg-green-600 hover:bg-green-500'
        } ${executing ? 'opacity-50 cursor-not-allowed' : ''}`}
        onClick={handleExecute}
        disabled={executing}
      >
        {executing
          ? 'Executing...'
          : dryRun
          ? 'Execute (DRY RUN)'
          : 'Execute LIVE'}
      </button>

      {result && (
        <div
          className={`p-3 rounded text-sm ${
            result.success
              ? 'bg-green-900/30 border border-green-800 text-green-300'
              : 'bg-red-900/30 border border-red-800 text-red-300'
          }`}
        >
          {result.success ? (
            <p>Order executed! Profit: {centsToDollars(result.realized_profit_cents)}</p>
          ) : (
            <p>Failed: {result.error_message || 'Unknown error'}</p>
          )}
          {result.dry_run && (
            <p className="text-yellow-400 text-xs mt-1">This was a dry run (simulated)</p>
          )}
        </div>
      )}
    </div>
  )
}
