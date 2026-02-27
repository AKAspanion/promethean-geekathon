'use client';

import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import type { AgentStatus, Supplier } from '@/lib/api';

type AgentStatusMessage = {
  type: 'agent_status';
  status: AgentStatus;
};

type SuppliersSnapshotMessage = {
  type: 'suppliers_snapshot';
  oemId: string;
  suppliers: Supplier[];
};

type NotificationMessage = AgentStatusMessage | SuppliersSnapshotMessage;

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

