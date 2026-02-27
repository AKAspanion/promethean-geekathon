import { SupplierDetailClient } from './SupplierDetailClient';

interface SupplierDetailPageProps {
  params: Promise<{ id: string }>;
}

export default async function SupplierDetailPage({ params }: SupplierDetailPageProps) {
  const { id } = await params;
  return <SupplierDetailClient id={id} />;
}

