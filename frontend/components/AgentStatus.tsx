"use client";

import { useEffect, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { agentApi, AgentStatus as AgentStatusType } from "@/lib/api";
import { useStreamingText } from "@/hooks/useStreamingText";
import { formatDistanceToNow } from "date-fns";
import { CircularScore, getScoreTextClass } from "@/components/CircularScore";

const statusColors: Record<string, string> = {
  idle: "bg-medium-gray",
  monitoring: "bg-primary-light",
  analyzing: "bg-cyan-blue",
  processing: "bg-primary-dark",
  completed: "bg-green-500",
  error: "bg-red-500",
};

const statusLabels: Record<string, string> = {
  idle: "Idle",
  monitoring: "Monitoring",
  analyzing: "Analyzing",
  processing: "Processing",
  completed: "Completed",
  error: "Error",
};

function StreamingTaskText({ text }: { text: string }) {
  const { displayed, isStreaming } = useStreamingText(text);

  return (
    <div className="flex items-start gap-2 min-h-5">
      <div className="shrink-0 -mt-0.5">
        {isStreaming ? (
          <span className="relative flex h-2 w-2 mt-[11px]">
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
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [history.length, expanded]);

  if (history.length <= 1) return null;

  return (
    <div className="relative mb-4">
      <div
        ref={containerRef}
        className={`overflow-y-auto rounded-lg bg-off-white dark:bg-gray-900/50 border border-light-gray dark:border-gray-700 px-3 py-2 space-y-1 scroll-smooth transition-all duration-300 ${
          expanded ? "max-h-[50vh]" : "max-h-24"
        }`}
      >
        {history.slice(0, -1).map((entry, i) => (
          <div
            key={`${i}-${entry}`}
            className="flex items-center gap-2 text-xs text-medium-gray dark:text-gray-500"
          >
            <span className="inline-flex h-1.5 w-1.5 rounded-full bg-light-gray dark:bg-gray-600 shrink-0" />
            <span className="truncate">{entry}</span>
          </div>
        ))}
      </div>
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        className="absolute -bottom-3 right-3 w-6 h-6 flex items-center justify-center rounded-full bg-primary-dark text-white shadow-md hover:bg-primary-light transition-colors"
        title={expanded ? "Collapse logs" : "Expand logs"}
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className={`w-3.5 h-3.5 transition-transform duration-300 ${expanded ? "rotate-180" : ""}`}
        >
          <path
            fillRule="evenodd"
            d="M5.22 8.22a.75.75 0 0 1 1.06 0L10 11.94l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 9.28a.75.75 0 0 1 0-1.06Z"
            clipRule="evenodd"
          />
        </svg>
      </button>
    </div>
  );
}

export function AgentStatus() {
  const queryClient = useQueryClient();
  const { data: status, isLoading } = useQuery<AgentStatusType>({
    queryKey: ["agent-status"],
    queryFn: agentApi.getStatus,
  });

  const triggerMutation = useMutation({
    mutationFn: agentApi.triggerAnalysisV2,
    onMutate: () => {
      // Clear previous logs and counters so the UI starts fresh
      setTaskHistory([]);
      setPrevTask(undefined);
      queryClient.setQueryData<AgentStatusType | undefined>(
        ["agent-status"],
        (prev) =>
          prev
            ? {
                ...prev,
                status: "analyzing" as const,
                currentTask: undefined,
                errorMessage: undefined,
                risksDetected: 0,
                opportunitiesIdentified: 0,
                plansGenerated: 0,
                lastUpdated: new Date().toISOString(),
              }
            : prev,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["agent-status"] });
      queryClient.invalidateQueries({ queryKey: ["risks"] });
      queryClient.invalidateQueries({ queryKey: ["opportunities"] });
      queryClient.invalidateQueries({ queryKey: ["mitigation-plans"] });
      queryClient.invalidateQueries({ queryKey: ["suppliers"] });
    },
  });

  // Accumulate task history — "adjust state during render" pattern (React-recommended)
  const [taskHistory, setTaskHistory] = useState<string[]>([]);
  const [prevStatus, setPrevStatus] = useState<string | undefined>(undefined);
  const [prevTask, setPrevTask] = useState<string | undefined>(undefined);

  if (status?.status !== prevStatus) {
    setPrevStatus(status?.status);
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

  const isActive = ["analyzing", "processing", "monitoring"].includes(
    status.status,
  );

  return (
    <div className="bg-white dark:bg-gray-800 rounded-lg shadow border border-light-gray dark:border-gray-700 p-6 space-y-4">
      {/* Row 1: Agent Status label | status badge + time | gap | Trigger button */}
      <div className="flex items-center gap-4">
        <h2 className="heading-3 text-dark-gray dark:text-gray-200 shrink-0">
          Agent Status
        </h2>
        <div className="flex items-center gap-2">
          <div
            className={`w-2.5 h-2.5 rounded-full ${statusColors[status.status]} ${isActive ? "animate-pulse" : ""}`}
          />
          <span className="text-sm font-medium text-dark-gray dark:text-gray-300">
            {statusLabels[status.status]}
          </span>
          {status.lastUpdated && (
            <span className="text-xs text-medium-gray dark:text-gray-400 ml-1">
              &middot;{" "}
              {formatDistanceToNow(new Date(status.lastUpdated), {
                addSuffix: true,
              })}
            </span>
          )}
        </div>
        <div className="flex-1" />
        {status.riskScore != null && (
          <div className="flex items-center gap-2 shrink-0">
            <CircularScore score={status.riskScore} size="sm" />
            <div className="leading-tight">
              <span className="text-[10px] font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider">
                OEM Risk
              </span>
              <div
                className={`text-sm font-bold ${getScoreTextClass(status.riskScore)}`}
              >
                {status.riskScore.toFixed(1)}
              </div>
            </div>
          </div>
        )}
        <button
          type="button"
          onClick={() => triggerMutation.mutate()}
          disabled={triggerMutation.isPending || isActive}
          className="px-5 py-2 bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors text-sm shrink-0"
        >
          {triggerMutation.isPending || isActive ? "Running..." : "Trigger Analysis"}
        </button>
      </div>

      {/* Row 2: Logs — visible until next trigger */}
      {taskHistory.length > 1 && (
        <StatusLogFeed history={taskHistory} />
      )}

      {/* Row 3: Current agent task / error */}
      {(status.currentTask || status.errorMessage) && (
        <div className="pt-3 border-t border-light-gray dark:border-gray-700 space-y-3">
          {status.currentTask && <StreamingTaskText text={status.currentTask} />}

          {status.errorMessage && (
            <div className="bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg p-3">
              <p className="text-sm text-red-800 dark:text-red-300">
                {status.errorMessage}
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
