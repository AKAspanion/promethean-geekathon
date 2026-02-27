'use client';

import { NewsRiskDashboard } from '@/components/NewsRiskDashboard';

export default function NewsRiskPage() {
  return (
    <>
      <div>
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">
          News Agent
        </h2>
        <p className="body-text text-medium-gray dark:text-gray-400">
          Supply chain &amp; logistics risks · sourced from NewsAPI + GDELT
        </p>
      </div>
      <NewsRiskDashboard />
    </>
  );
}
