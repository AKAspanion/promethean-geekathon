"use client";

interface AgentSummaryCardProps {
  summary: string;
}

export function AgentSummaryCard({ summary }: AgentSummaryCardProps) {
  return (
    <div className="rounded-2xl border border-cyan-blue/40 dark:border-cyan-blue/30 bg-cyan-blue/5 dark:bg-gray-700/50 p-5">
      <div className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-primary-dark dark:text-primary-light">
        Agent summary
      </div>
      <p className="whitespace-pre-line text-[16px] leading-relaxed text-dark-gray dark:text-gray-300">
        {summary}
      </p>
    </div>
  );
}
