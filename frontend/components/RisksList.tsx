'use client';

import { useQuery } from '@tanstack/react-query';
import { risksApi, Risk } from '@/lib/api';
import { safeFormatDistanceToNow } from '@/lib/format-date';

const severityColors = {
  low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const statusColors = {
  detected: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  analyzing: 'bg-purple-100 text-purple-800 dark:bg-purple-900/30 dark:text-purple-400',
  mitigating: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  false_positive: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
};

export function RisksList() {
  const { data: risks, isLoading } = useQuery<Risk[]>({
    queryKey: ['risks'],
    queryFn: () => risksApi.getAll(),
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Risks</h2>
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="animate-pulse">
              <div className="h-4 bg-light-gray dark:bg-gray-700 rounded w-3/4 mb-2"></div>
              <div className="h-3 bg-light-gray dark:bg-gray-700 rounded w-full"></div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (!risks || risks.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Risks</h2>
        <p className="body-text text-medium-gray dark:text-gray-400">No risks detected</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
      <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Risks</h2>
      <div className="space-y-4">
        {risks.slice(0, 10).map(risk => (
          <div
            key={risk.id}
            className="border border-light-gray dark:border-gray-600 rounded-lg p-4 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <h3 className="heading-3 text-dark-gray dark:text-gray-200">{risk.title}</h3>
              <div className="flex gap-2">
                <span className={`px-2 py-1 rounded-lg text-xs font-medium ${severityColors[risk.severity]}`}>
                  {risk.severity}
                </span>
                <span className={`px-2 py-1 rounded-lg text-xs font-medium ${statusColors[risk.status]}`}>
                  {risk.status.replace('_', ' ')}
                </span>
              </div>
            </div>
            <p className="body-text text-medium-gray dark:text-gray-400 mb-2">{risk.description}</p>
            <div className="flex flex-wrap gap-4 text-xs text-medium-gray dark:text-gray-400">
              {risk.affectedRegion && <span>📍 {risk.affectedRegion}</span>}
              {risk.estimatedCost && <span>💰 ${risk.estimatedCost.toLocaleString()}</span>}
              {risk.mitigationPlans && risk.mitigationPlans.length > 0 && (
                <span>📋 {risk.mitigationPlans.length} plan(s)</span>
              )}
              <span>{safeFormatDistanceToNow(risk.createdAt, { addSuffix: true })}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
