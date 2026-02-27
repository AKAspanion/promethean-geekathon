'use client';

import { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { agentApi, AgentStatus as AgentStatusType } from '@/lib/api';
import { useStreamingText } from '@/hooks/useStreamingText';
import { formatDistanceToNow } from 'date-fns';

const statusColors: Record<string, string> = {
  idle: 'bg-medium-gray',
  monitoring: 'bg-primary-light',
  analyzing: 'bg-cyan-blue',
  processing: 'bg-primary-dark',
  completed: 'bg-green-500',
  error: 'bg-red-500',
};

const statusLabels: Record<string, string> = {
  idle: 'Idle',
  monitoring: 'Monitoring',
  analyzing: 'Analyzing',
  processing: 'Processing',
  completed: 'Completed',
  error: 'Error',
};

function StreamingTaskText({ text }: { text: string }) {
  const { displayed, isStreaming } = useStreamingText(text);

  return (
    <div className="flex items-start gap-2 mb-4 min-h-6">
      <div className="shrink-0 -mt-0.5">
        {isStreaming ? (
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-blue opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-blue" />
          </span>
        ) : (
          <span className="inline-flex h-2 w-2 rounded-full bg-primary-light" />
        )}
      </div>
      <p className="body-text text-medium-gray dark:text-gray-400 leading-relaxed">
        {displayed}
        {isStreaming && (
          <span className="inline-block w-0.5 h-[1em] bg-cyan-blue dark:bg-cyan-400 ml-px align-text-bottom animate-pulse" />
        )}
      </p>
    </div>
  );
}

function StatusLogFeed({ history }: { history: string[] }) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [history.length]);

  if (history.length <= 1) return null;

  return (
    <div
      ref={containerRef}
      className="mb-4 max-h-24 overflow-y-auto rounded-lg bg-off-white dark:bg-gray-900/50 border border-light-gray dark:border-gray-700 px-3 py-2 space-y-1 scroll-smooth"
    >
      {history.slice(0, -1).map((entry, i) => (
        <div key={`${i}-${entry}`} className="flex items-center gap-2 text-xs text-medium-gray dark:text-gray-500">
          <span className="inline-flex h-1.5 w-1.5 rounded-full bg-light-gray dark:bg-gray-600 shrink-0" />
          <span className="truncate">{entry}</span>
        </div>
      ))}
    </div>
  );
}

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

  // Accumulate task history — "adjust state during render" pattern (React-recommended)
  const [taskHistory, setTaskHistory] = useState<string[]>([]);
  const [prevStatus, setPrevStatus] = useState<string | undefined>(undefined);
  const [prevTask, setPrevTask] = useState<string | undefined>(undefined);

  if (status?.status !== prevStatus) {
    setPrevStatus(status?.status);
    if (status?.status === 'idle') {
      setTaskHistory([]);
      setPrevTask(undefined);
    }
  }

  const currentTask = status?.currentTask;
  if (currentTask !== prevTask) {
    setPrevTask(currentTask);
    if (currentTask && taskHistory[taskHistory.length - 1] !== currentTask) {
      setTaskHistory([...taskHistory, currentTask]);
    }
  }

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

  const isActive = ['analyzing', 'processing', 'monitoring'].includes(status.status);

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6">
      <div className="flex items-center justify-between mb-4">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">Agent Status</h2>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => triggerMutation.mutate()}
            disabled={triggerMutation.isPending || isActive}
            className="px-5 py-2.5 bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors text-base"
          >
            {triggerMutation.isPending ? 'Triggering...' : isActive ? 'Running...' : 'Trigger Analysis'}
          </button>
          <div className="flex items-center gap-2">
            <div className={`w-3 h-3 rounded-full ${statusColors[status.status]} ${isActive ? 'animate-pulse' : ''}`} />
            <span className="text-sm font-medium text-dark-gray dark:text-gray-300">
              {statusLabels[status.status]}
            </span>
          </div>
        </div>
      </div>

      {status.currentTask && (
        <>
          <StatusLogFeed history={taskHistory} />
          <StreamingTaskText text={status.currentTask} />
        </>
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

      {status.riskScore != null && (
        <div className="mt-4 pt-4 border-t border-light-gray dark:border-gray-700">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider">
              OEM Risk Score
            </span>
            <span className={`text-lg font-bold ${
              status.riskScore <= 25 ? 'text-green-600 dark:text-green-400' :
              status.riskScore <= 50 ? 'text-yellow-600 dark:text-yellow-400' :
              status.riskScore <= 75 ? 'text-orange-600 dark:text-orange-400' :
              'text-red-600 dark:text-red-400'
            }`}>
              {status.riskScore.toFixed(1)}/100
            </span>
          </div>
          <div className="mt-2 w-full bg-light-gray dark:bg-gray-700 rounded-full h-2">
            <div
              className={`h-2 rounded-full transition-all duration-500 ${
                status.riskScore <= 25 ? 'bg-green-500' :
                status.riskScore <= 50 ? 'bg-yellow-500' :
                status.riskScore <= 75 ? 'bg-orange-500' :
                'bg-red-500'
              }`}
              style={{ width: `${Math.min(100, status.riskScore)}%` }}
            />
          </div>
        </div>
      )}

      {status.lastUpdated && (
        <p className="text-xs text-medium-gray dark:text-gray-400 mt-4">
          Last updated: {formatDistanceToNow(new Date(status.lastUpdated), { addSuffix: true })}
        </p>
      )}
    </div>
  );
}
