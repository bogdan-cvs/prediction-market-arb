import { useState } from 'react'
import OpportunityTable from './OpportunityTable'
import ExecutionPanel from './ExecutionPanel'
import PortfolioView from './PortfolioView'
import ProfitTracker from './ProfitTracker'
import MarketMatcher from './MarketMatcher'
import Settings from './Settings'

const TABS = ['Opportunities', 'Matches', 'History', 'Settings']

export default function Dashboard({
  opportunities,
  mode,
  loading,
  onScan,
  onExecute,
  onToggleMode,
}) {
  const [selectedOpp, setSelectedOpp] = useState(null)
  const [activeTab, setActiveTab] = useState('Opportunities')

  return (
    <div className="flex flex-col h-full gap-4">
      {/* Portfolio summary top bar */}
      <PortfolioView />

      {/* Tab navigation */}
      <div className="flex gap-1 border-b border-gray-800">
        {TABS.map((tab) => (
          <button
            key={tab}
            className={`px-4 py-2 text-sm transition-colors ${
              activeTab === tab
                ? 'text-blue-400 border-b-2 border-blue-400'
                : 'text-gray-500 hover:text-gray-300'
            }`}
            onClick={() => setActiveTab(tab)}
          >
            {tab}
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2">
          <button
            className="px-3 py-1 text-xs rounded bg-gray-800 hover:bg-gray-700 transition-colors"
            onClick={onScan}
            disabled={loading}
          >
            {loading ? 'Scanning...' : 'Scan Now'}
          </button>
          <span className="text-xs text-gray-500">
            {opportunities.length} opportunities
          </span>
        </div>
      </div>

      {/* Main content */}
      <div className="flex gap-4 flex-1 min-h-0">
        {/* Left panel */}
        <div className="flex-1 overflow-auto">
          {activeTab === 'Opportunities' && (
            <OpportunityTable
              opportunities={opportunities}
              onSelect={setSelectedOpp}
              selectedId={selectedOpp?.opportunity_id}
            />
          )}
          {activeTab === 'Matches' && <MarketMatcher />}
          {activeTab === 'History' && <ProfitTracker />}
          {activeTab === 'Settings' && (
            <Settings mode={mode} onToggleMode={onToggleMode} />
          )}
        </div>

        {/* Right panel - execution */}
        {activeTab === 'Opportunities' && (
          <div className="w-80 shrink-0 bg-gray-900/50 rounded-lg p-4 overflow-auto">
            <ExecutionPanel
              opportunity={selectedOpp}
              onExecute={onExecute}
              dryRun={mode.dry_run}
            />
          </div>
        )}
      </div>
    </div>
  )
}
