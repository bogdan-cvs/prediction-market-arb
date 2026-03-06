import { centsToPrice, centsToDollars, profitColor, platformLabel } from '../utils/formatting'

export default function OpportunityTable({ opportunities, onSelect, selectedId }) {
  if (!opportunities.length) {
    return (
      <div className="flex items-center justify-center h-48 text-gray-500">
        <div className="text-center">
          <p className="text-lg">No opportunities detected</p>
          <p className="text-sm mt-1">Scanner is running...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-800 text-gray-400 text-left">
            <th className="pb-2 pr-3">Market</th>
            <th className="pb-2 pr-3">Leg A</th>
            <th className="pb-2 pr-3">Leg B</th>
            <th className="pb-2 pr-3 text-right">Cost</th>
            <th className="pb-2 pr-3 text-right">Gross</th>
            <th className="pb-2 pr-3 text-right">Fees</th>
            <th className="pb-2 pr-3 text-right">Net</th>
            <th className="pb-2 pr-3 text-right">ROI</th>
            <th className="pb-2 pr-3 text-right">Qty</th>
            <th className="pb-2 pr-3 text-right">Max $</th>
            <th className="pb-2"></th>
          </tr>
        </thead>
        <tbody>
          {opportunities.map((opp) => (
            <tr
              key={opp.opportunity_id}
              className={`border-b border-gray-900 hover:bg-gray-900/50 cursor-pointer transition-colors ${
                selectedId === opp.opportunity_id ? 'bg-gray-900' : ''
              }`}
              onClick={() => onSelect(opp)}
            >
              <td className="py-2 pr-3 max-w-[400px]" title={opp.market_title}>
                <span className="break-words">{opp.market_title}</span>
              </td>
              <td className="py-2 pr-3">
                <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800">
                  {platformLabel(opp.leg_a?.platform)}
                </span>
                <span className="ml-1 text-gray-300">
                  {opp.leg_a?.side} @ {centsToPrice(opp.leg_a?.price_cents)}
                </span>
              </td>
              <td className="py-2 pr-3">
                <span className="text-xs px-1.5 py-0.5 rounded bg-gray-800">
                  {platformLabel(opp.leg_b?.platform)}
                </span>
                <span className="ml-1 text-gray-300">
                  {opp.leg_b?.side} @ {centsToPrice(opp.leg_b?.price_cents)}
                </span>
              </td>
              <td className="py-2 pr-3 text-right text-gray-300">
                {centsToPrice(opp.total_cost_cents)}
              </td>
              <td className="py-2 pr-3 text-right text-green-400">
                {centsToPrice(opp.gross_profit_cents)}
              </td>
              <td className="py-2 pr-3 text-right text-red-400">
                {centsToPrice(opp.fees_cents)}
              </td>
              <td className={`py-2 pr-3 text-right font-medium ${profitColor(opp.net_profit_cents)}`}>
                {centsToPrice(opp.net_profit_cents)}
              </td>
              <td className="py-2 pr-3 text-right text-gray-300">
                {opp.net_profit_pct}%
              </td>
              <td className="py-2 pr-3 text-right text-gray-400">
                {opp.max_quantity}
              </td>
              <td className="py-2 pr-3 text-right font-medium text-green-400">
                {centsToDollars(opp.net_profit_cents * opp.max_quantity)}
              </td>
              <td className="py-2">
                <button
                  className="px-2 py-1 text-xs rounded bg-blue-600 hover:bg-blue-500 transition-colors"
                  onClick={(e) => {
                    e.stopPropagation()
                    onSelect(opp)
                  }}
                >
                  Trade
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
