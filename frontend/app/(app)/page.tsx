'use client';

import { AgentStatus } from '@/components/AgentStatus';
import { RisksList } from '@/components/RisksList';
import { OpportunitiesList } from '@/components/OpportunitiesList';
import { MitigationPlansList } from '@/components/MitigationPlansList';
import { SuppliersList } from '@/components/SuppliersList';
import { useWebSocketNotifications } from '@/hooks/useWebSocketNotifications';

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
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <RisksList />
        <OpportunitiesList />
      </div>
      <div className="mb-6">
        <MitigationPlansList />
      </div>
    </>
  );
}
