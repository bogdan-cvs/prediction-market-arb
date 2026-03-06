export function centsToDollars(cents) {
  if (cents == null) return '-'
  return `$${(cents / 100).toFixed(2)}`
}

export function centsToPrice(cents) {
  if (cents == null) return '-'
  return `${cents}¢`
}

export function profitColor(cents) {
  if (cents > 3) return 'text-green-400'
  if (cents > 1) return 'text-yellow-400'
  if (cents > 0) return 'text-yellow-300'
  return 'text-red-400'
}

export function platformLabel(platform) {
  const labels = {
    kalshi: 'Kalshi',
    polymarket: 'Polymarket',
    limitless: 'Limitless',
    ibkr: 'ForecastEx',
  }
  return labels[platform] || platform
}

export function platformColor(platform) {
  const colors = {
    kalshi: 'bg-blue-600',
    polymarket: 'bg-purple-600',
    limitless: 'bg-orange-600',
    ibkr: 'bg-emerald-600',
  }
  return colors[platform] || 'bg-gray-600'
}

export function marketUrl(platform, marketId) {
  if (platform === 'kalshi') {
    // Kalshi market ticker format: KXPGATOP20-ARPIPBM26-PCOO
    // Event ticker is everything except the last segment
    const parts = marketId.split('-')
    const eventTicker = parts.slice(0, -1).join('-')
    return `https://kalshi.com/markets/${eventTicker}`
  }
  if (platform === 'polymarket') {
    return `https://polymarket.com/event/${marketId}`
  }
  return '#'
}

export function timeAgo(dateStr) {
  if (!dateStr) return ''
  const diff = Date.now() - new Date(dateStr).getTime()
  const secs = Math.floor(diff / 1000)
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  return `${hours}h ago`
}
