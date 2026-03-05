import { useState, useEffect } from 'react'

export default function Settings({ mode, onToggleMode }) {
  return (
    <div className="space-y-4">
      <h3 className="font-medium text-gray-200">Settings</h3>

      <div className="space-y-3">
        <div className="flex items-center justify-between bg-gray-900 rounded p-3">
          <div>
            <p className="text-sm font-medium">Execution Mode</p>
            <p className="text-xs text-gray-400">
              {mode.dry_run
                ? 'DRY RUN - Orders are simulated, not sent to exchanges'
                : 'LIVE - Orders will be sent to real exchanges'}
            </p>
          </div>
          <button
            className={`px-4 py-2 rounded text-sm font-medium transition-colors ${
              mode.dry_run
                ? 'bg-yellow-600 text-black hover:bg-yellow-500'
                : 'bg-red-600 hover:bg-red-500'
            }`}
            onClick={onToggleMode}
          >
            {mode.dry_run ? 'DRY RUN' : 'LIVE'}
          </button>
        </div>

        <div className="bg-gray-900 rounded p-3 text-sm space-y-2">
          <p className="font-medium text-gray-200">Risk Parameters</p>
          <div className="grid grid-cols-2 gap-2 text-xs">
            <div className="text-gray-400">Max exposure per market:</div>
            <div>$100</div>
            <div className="text-gray-400">Max total exposure:</div>
            <div>$1,000</div>
            <div className="text-gray-400">Max daily loss:</div>
            <div>$50</div>
            <div className="text-gray-400">Min profit threshold:</div>
            <div>2 cents</div>
            <div className="text-gray-400">Min quantity:</div>
            <div>10 contracts</div>
            <div className="text-gray-400">Scan interval:</div>
            <div>3 seconds</div>
          </div>
          <p className="text-xs text-gray-500 mt-2">
            Edit .env file to change these parameters. Restart backend to apply.
          </p>
        </div>
      </div>
    </div>
  )
}
