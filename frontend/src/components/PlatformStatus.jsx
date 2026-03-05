import { platformLabel, platformColor } from '../utils/formatting'

export default function PlatformStatus({ platforms, wsConnected }) {
  const allPlatforms = ['kalshi', 'polymarket', 'limitless', 'ibkr']

  return (
    <div className="flex items-center gap-3">
      {allPlatforms.map((p) => {
        const connected = platforms[p] === true
        return (
          <div key={p} className="flex items-center gap-1.5">
            <div
              className={`w-2 h-2 rounded-full ${
                connected ? 'bg-green-400 animate-pulse' : 'bg-red-500'
              }`}
            />
            <span className="text-xs text-gray-400">{platformLabel(p)}</span>
          </div>
        )
      })}
      <div className="ml-2 flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full ${
            wsConnected ? 'bg-green-400' : 'bg-red-500'
          }`}
        />
        <span className="text-xs text-gray-400">WS</span>
      </div>
    </div>
  )
}
