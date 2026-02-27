'use client';

import { useQuery } from '@tanstack/react-query';
import { mitigationPlansApi, MitigationPlan } from '@/lib/api';
import { formatDistanceToNow } from 'date-fns';

const statusColors = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900/30 dark:text-gray-400',
  approved: 'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  in_progress: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  completed: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

export function MitigationPlansList() {
  const { data: plans, isLoading } = useQuery<MitigationPlan[]>({
    queryKey: ['mitigation-plans'],
    queryFn: () => mitigationPlansApi.getAll(),
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Mitigation Plans</h2>
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

  if (!plans || plans.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Mitigation Plans</h2>
        <p className="body-text text-medium-gray dark:text-gray-400">No mitigation plans available</p>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
      <h2 className="heading-3 text-dark-gray dark:text-gray-200 mb-4">Mitigation Plans</h2>
      <div className="space-y-4">
        {plans.slice(0, 10).map(plan => (
          <div
            key={plan.id}
            className="border border-light-gray dark:border-gray-600 rounded-lg p-4 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
          >
            <div className="flex items-start justify-between mb-2">
              <h3 className="heading-3 text-dark-gray dark:text-gray-200">{plan.title}</h3>
              <span className={`px-2 py-1 rounded-lg text-xs font-medium ${statusColors[plan.status]}`}>
                {plan.status.replace('_', ' ')}
              </span>
            </div>
            <p className="body-text text-medium-gray dark:text-gray-400 mb-3">{plan.description}</p>
            {plan.actions && plan.actions.length > 0 && (
              <div className="mb-3">
                <h4 className="text-xs font-semibold text-dark-gray dark:text-gray-200 mb-2">Actions:</h4>
                <ul className="list-disc list-inside space-y-1">
                  {plan.actions.slice(0, 3).map((action, idx) => (
                    <li key={idx} className="text-xs text-medium-gray dark:text-gray-400">
                      {action}
                    </li>
                  ))}
                  {plan.actions.length > 3 && (
                    <li className="text-xs text-medium-gray dark:text-gray-400">
                      +{plan.actions.length - 3} more
                    </li>
                  )}
                </ul>
              </div>
            )}
            <div className="flex flex-wrap gap-4 text-xs text-medium-gray dark:text-gray-400">
              {plan.risk && <span>⚠️ Risk: {plan.risk.title}</span>}
              {plan.opportunity && <span>✨ Opportunity: {plan.opportunity.title}</span>}
              {plan.assignedTo && <span>👤 {plan.assignedTo}</span>}
              {plan.dueDate && (
                <span>📅 Due: {new Date(plan.dueDate).toLocaleDateString()}</span>
              )}
              <span>{formatDistanceToNow(new Date(plan.createdAt), { addSuffix: true })}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
