'use client';

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentApi, AgentStatus as AgentStatusType } from '@/lib/api';
import { formatDistanceToNow } from 'date-fns';

const statusColors = {
  idle: 'bg-medium-gray',
  monitoring: 'bg-primary-light',
  analyzing: 'bg-cyan-blue',
  processing: 'bg-primary-dark',
  error: 'bg-red-500',
};

const statusLabels = {
  idle: 'Idle',
  monitoring: 'Monitoring',
  analyzing: 'Analyzing',
  processing: 'Processing',
  error: 'Error',
};

export function AgentStatus() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery<AgentStatusType>({
    queryKey: ['agent-status'],
    queryFn: agentApi.getStatus,
  });
  const triggerMutation = useMutation({
    mutationFn: agentApi.triggerAnalysisV2,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['agent-status'] });
      queryClient.invalidateQueries({ queryKey: ['risks'] });
      queryClient.invalidateQueries({ queryKey: ['opportunities'] });
      queryClient.invalidateQueries({ queryKey: ['mitigation-plans'] });
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
    },
  });

  if (isLoading) {
    return (
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
        <div className="animate-pulse">
          <div className="h-4 bg-light-gray dark:bg-gray-700 rounded w-1/4 mb-4"></div>
          <div className="h-8 bg-light-gray dark:bg-gray-700 rounded"></div>
        </div>
      </div>
    );
  }

  if (!status) return null;

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">Agent Status</h2>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => triggerMutation.mutate()}
            disabled={triggerMutation.isPending}
            className="px-5 py-2.5 bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors text-base"
          >
            {triggerMutation.isPending ? 'Triggering...' : 'Trigger Analysis'}
          </button>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${statusColors[status.status]}`}></div>
            <span className="text-sm font-medium text-dark-gray dark:text-gray-300">
              {statusLabels[status.status]}
            </span>
          </div>
        </div>
      </div>

      {status.currentTask && (
        <p className="body-text text-medium-gray dark:text-gray-400 mb-4">{status.currentTask}</p>
      )}

      {status.errorMessage && (
        <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3 mb-4">
          <p className="text-sm text-red-800 dark:text-red-300">{status.errorMessage}</p>
        </div>
      )}

      <div className="grid grid-cols-3 gap-4 mt-4">
        <div className="text-center">
          <div className="text-2xl font-bold text-dark-gray dark:text-gray-200">{status.risksDetected}</div>
          <div className="text-xs text-medium-gray dark:text-gray-400">Risks Detected</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-cyan-blue">
            {status.opportunitiesIdentified}
          </div>
          <div className="text-xs text-medium-gray dark:text-gray-400">Opportunities</div>
        </div>
        <div className="text-center">
          <div className="text-2xl font-bold text-primary-light">{status.plansGenerated}</div>
          <div className="text-xs text-medium-gray dark:text-gray-400">Plans Generated</div>
        </div>
      </div>

      {status.lastUpdated && (
        <p className="text-xs text-medium-gray dark:text-gray-400 mt-4">
          Last updated: {formatDistanceToNow(new Date(status.lastUpdated), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}
