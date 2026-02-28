import { AnalysisReportClient } from "./AnalysisReportClient";

interface AnalysisReportPageProps {
  params: Promise<{ id: string; sraId: string }>;
}

export default async function AnalysisReportPage({
  params,
}: AnalysisReportPageProps) {
  const { id, sraId } = await params;
  return <AnalysisReportClient supplierId={id} sraId={sraId} />;
}
