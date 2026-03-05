import useWebSocket from './hooks/useWebSocket'
import useArbitrage from './hooks/useArbitrage'
import Dashboard from './components/Dashboard'
import PlatformStatus from './components/PlatformStatus'

export default function App() {
  const { connected: wsConnected, subscribe } = useWebSocket()
  const {
    opportunities,
    platforms,
    mode,
    loading,
    triggerScan,
    executeOpportunity,
    toggleMode,
  } = useArbitrage(subscribe)

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100">
      {/* Top bar */}
      <header className="flex items-center justify-between px-6 py-3 border-b border-gray-800 bg-gray-950/80 backdrop-blur">
        <div className="flex items-center gap-4">
          <h1 className="text-lg font-semibold tracking-tight">
            Prediction Market Arb
          </h1>
          <span
            className={`px-2 py-0.5 rounded text-xs font-medium ${
              mode.dry_run
                ? 'bg-yellow-600 text-black'
                : 'bg-red-600 text-white'
            }`}
          >
            {mode.dry_run ? 'DRY RUN' : 'LIVE'}
          </span>
        </div>
        <PlatformStatus platforms={platforms} wsConnected={wsConnected} />
      </header>

      {/* Main content */}
      <main className="flex-1 p-6 overflow-hidden">
        <Dashboard
          opportunities={opportunities}
          mode={mode}
          loading={loading}
          onScan={triggerScan}
          onExecute={executeOpportunity}
          onToggleMode={toggleMode}
        />
      </main>
    </div>
  )
}
