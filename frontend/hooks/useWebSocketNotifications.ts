'use client';

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { AgentStatus, Supplier, SupplyChainRiskScore } from '@/lib/api';

type AgentStatusMessage = {
  type: 'agent_status';
  status: AgentStatus;
};

type SuppliersSnapshotMessage = {
  type: 'suppliers_snapshot';
  oemId: string;
  suppliers: Supplier[];
};

type NewsAgentProgressMessage = {
  type: 'news_agent_progress';
  step: string;
  message: string;
  context?: string;
  oemName?: string;
  supplierName?: string;
  details?: Record<string, unknown>;
};

type OemRiskScoreMessage = {
  type: 'oem_risk_score';
  oemId: string;
  score: SupplyChainRiskScore;
};

type NotificationMessage =
  | AgentStatusMessage
  | SuppliersSnapshotMessage
  | NewsAgentProgressMessage
  | OemRiskScoreMessage;

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

const WS_BASE_URL = API_BASE_URL.replace(/^http/, 'ws').replace(/\/$/, '');

export function useWebSocketNotifications() {
  const queryClient = useQueryClient();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const socket = new WebSocket(`${WS_BASE_URL}/ws`);
    socketRef.current = socket;

    socket.onopen = () => {
      console.log('[WS] Connected to backend notifications');
    };

    socket.onmessage = (event: MessageEvent<string>) => {
      try {
        const data: NotificationMessage = JSON.parse(event.data);

        if (data.type === 'agent_status') {
          console.log('[WS] agent_status', {
            status: data.status.status,
            currentTask: data.status.currentTask,
            supplierName: data.status.supplierName,
            oemName: data.status.oemName,
            risksDetected: data.status.risksDetected,
            opportunitiesIdentified: data.status.opportunitiesIdentified,
            plansGenerated: data.status.plansGenerated,
          });
          queryClient.setQueryData<AgentStatus | undefined>(
            ['agent-status'],
            data.status,
          );
        }

        if (data.type === 'suppliers_snapshot') {
          console.log('[WS] suppliers_snapshot', {
            oemId: data.oemId,
            supplierCount: data.suppliers.length,
            suppliers: data.suppliers,
          });
          queryClient.setQueryData<Supplier[] | undefined>(
            ['suppliers'],
            data.suppliers,
          );
        }

        if (data.type === 'oem_risk_score') {
          console.log('[WS] oem_risk_score', {
            oemId: data.oemId,
            overallScore: data.score.overallScore,
            summary: data.score.summary,
          });
          queryClient.setQueryData<SupplyChainRiskScore | undefined>(
            ['oem-risk-score'],
            data.score,
          );
        }

        if (data.type === 'news_agent_progress') {
          console.log('[WS] news_agent_progress', {
            step: data.step,
            message: data.message,
            context: data.context,
            supplierName: data.supplierName,
            oemName: data.oemName,
            details: data.details,
          });
          // Merge into agent-status so AgentStatus component shows progress
          queryClient.setQueryData<AgentStatus | undefined>(
            ['agent-status'],
            (prev) => {
              if (!prev) return prev;
              const isCompleted = data.step === 'completed';
              const label = data.supplierName
                ? `[News - ${data.supplierName}]`
                : '[News]';
              return {
                ...prev,
                status: isCompleted ? 'completed' : 'analyzing',
                currentTask: `${label} ${data.message}`,
                lastUpdated: new Date().toISOString(),
                // Update counters when the news agent completes
                ...(isCompleted && data.details
                  ? {
                      risksDetected:
                        prev.risksDetected +
                        ((data.details.risks as number) || 0),
                      opportunitiesIdentified:
                        prev.opportunitiesIdentified +
                        ((data.details.opportunities as number) || 0),
                    }
                  : {}),
              };
            },
          );
        }
      } catch {
        console.warn('[WS] Failed to parse message', event.data);
      }
    };

    socket.onerror = () => {
      console.warn('[WS] Connection error');
    };

    socket.onclose = (event: CloseEvent) => {
      console.log('[WS] Disconnected', {
        code: event.code,
        reason: event.reason || 'none',
        wasClean: event.wasClean,
      });
    };

    return () => {
      if (socketRef.current) {
        socketRef.current.close();
        socketRef.current = null;
      }
    };
  }, [queryClient]);
}

