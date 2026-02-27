'use client';

import { ShippingRiskDashboard } from '@/components/ShippingRiskDashboard';

export default function ShippingRiskPage() {
  return (
    <>
      <div>
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">
          Shipping Risk Intelligence
        </h2>
        <p className="body-text text-medium-gray dark:text-gray-400">
          Manufacturing hub: Bangalore, India · Shipment Agent · LLM + Tracking
        </p>
      </div>
      <ShippingRiskDashboard />
    </>
  );
}
