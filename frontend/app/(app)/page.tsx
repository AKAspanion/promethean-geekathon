"use client";

import { AgentStatus } from "@/components/AgentStatus";
import { MitigationPlansList } from "@/components/MitigationPlansList";
import { SuppliersList } from "@/components/SuppliersList";
import { useWebSocketNotifications } from "@/hooks/useWebSocketNotifications";

export default function Home() {
  useWebSocketNotifications();

  return (
    <>
      <div className="mb-6">
        <AgentStatus />
      </div>
      <div className="mb-6">
        <SuppliersList />
      </div>
      <div className="mb-6">
        <MitigationPlansList />
      </div>
    </>
  );
}
