import React from 'react';
import { Link } from 'react-router-dom';
import { AudioLines } from 'lucide-react';

export default function TopBar({ projectName, step, totalSteps }) {
  return (
    <div className="w-full bg-surface/80 backdrop-blur-xl border-b border-border sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
        <Link to="/new" className="flex items-center gap-2 font-bold text-lg hover:opacity-80 transition-opacity group">
          <div className="w-8 h-8 rounded-lg bg-violet-600 flex items-center justify-center shadow-lg shadow-violet-500/20 group-hover:shadow-violet-500/40 transition-shadow">
            <AudioLines size={18} className="text-zinc-900" />
          </div>
          <span className="text-textPrimary tracking-tight">
            Aud<span className="text-violet-900 font-bold">Stories</span>
          </span>
        </Link>
        <div className="flex items-center space-x-6">
          <span className="text-sm font-medium text-textSecondary">{projectName}</span>
          {step && totalSteps && (
            <div className="flex items-center gap-2">
              <div className="h-2 w-16 bg-white rounded-full overflow-hidden">
                <div
                  className="h-full bg-gradient-to-r from-violet-500 to-violet-500 transition-all duration-500 ease-out"
                  style={{ width: `${(step / totalSteps) * 100}%` }}
                />
              </div>
              <span className="text-xs font-semibold text-textSecondary bg-white border border-zinc-200 px-2.5 py-1 rounded-full uppercase tracking-wider">
                Step {step} of {totalSteps}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
