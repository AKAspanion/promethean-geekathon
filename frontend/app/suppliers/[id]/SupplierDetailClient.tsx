'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { suppliersApi, type Supplier, type SupplierUpdatePayload } from '@/lib/api';
import { AppNav } from '@/components/AppNav';
import { useAuth } from '@/lib/auth-context';
import { formatDistanceToNow } from 'date-fns';

const severityBadgeClasses: Record<string, string> = {
  low: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  medium: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  high: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  critical: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

const swarmLevelBadgeClasses: Record<string, string> = {
  LOW: 'bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-400',
  MEDIUM: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-400',
  HIGH: 'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  CRITICAL: 'bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-400',
};

interface EditFormState {
  name: string;
  location: string;
  city: string;
  country: string;
  region: string;
  commodities: string;
}

function DeleteConfirmDialog({
  supplierName,
  onConfirm,
  onCancel,
  isPending,
}: {
  supplierName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-light-gray dark:border-gray-700 p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold text-dark-gray dark:text-gray-100 mb-2">
          Delete supplier
        </h3>
        <p className="text-sm text-medium-gray dark:text-gray-400 mb-6">
          Are you sure you want to delete{' '}
          <span className="font-medium text-dark-gray dark:text-gray-200">
            {supplierName}
          </span>
          ? This action cannot be undone.
        </p>
        <div className="flex justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            disabled={isPending}
            className="px-4 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isPending}
            className="px-4 py-2 rounded-lg text-sm font-semibold text-white bg-red-600 hover:bg-red-700 disabled:opacity-50 transition-colors"
          >
            {isPending ? 'Deleting…' : 'Delete'}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditForm({
  supplier,
  onSave,
  onCancel,
  isPending,
}: {
  supplier: Supplier;
  onSave: (data: SupplierUpdatePayload) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [form, setForm] = useState<EditFormState>({
    name: supplier.name ?? '',
    location: supplier.location ?? '',
    city: supplier.city ?? '',
    country: supplier.country ?? '',
    region: supplier.region ?? '',
    commodities: supplier.commodities ?? '',
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: SupplierUpdatePayload = {};
    if (form.name) payload.name = form.name;
    if (form.location !== undefined) payload.location = form.location || undefined;
    if (form.city !== undefined) payload.city = form.city || undefined;
    if (form.country !== undefined) payload.country = form.country || undefined;
    if (form.region !== undefined) payload.region = form.region || undefined;
    if (form.commodities !== undefined) payload.commodities = form.commodities || undefined;
    onSave(payload);
  };

  const labelClass = 'block text-xs font-medium text-medium-gray dark:text-gray-400 mb-1';
  const inputClass =
    'w-full rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-dark-gray dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-dark dark:focus:ring-primary-light';

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="sm:col-span-2">
          <label htmlFor="name" className={labelClass}>
            Name <span className="text-red-500">*</span>
          </label>
          <input
            id="name"
            name="name"
            type="text"
            required
            value={form.name}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="location" className={labelClass}>
            Location
          </label>
          <input
            id="location"
            name="location"
            type="text"
            value={form.location}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="city" className={labelClass}>
            City
          </label>
          <input
            id="city"
            name="city"
            type="text"
            value={form.city}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="country" className={labelClass}>
            Country
          </label>
          <input
            id="country"
            name="country"
            type="text"
            value={form.country}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div>
          <label htmlFor="region" className={labelClass}>
            Region
          </label>
          <input
            id="region"
            name="region"
            type="text"
            value={form.region}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
        <div className="sm:col-span-2">
          <label htmlFor="commodities" className={labelClass}>
            Commodities
          </label>
          <input
            id="commodities"
            name="commodities"
            type="text"
            value={form.commodities}
            onChange={handleChange}
            className={inputClass}
          />
        </div>
      </div>

      <div className="flex justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          disabled={isPending}
          className="px-4 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 disabled:opacity-50 transition-colors"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={isPending || !form.name}
          className="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
  );
}

export function SupplierDetailClient({ id }: { id: string }) {
  const router = useRouter();
  const { isLoggedIn, hydrated } = useAuth();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { data: supplier, isLoading } = useQuery({
    queryKey: ['supplier', id],
    queryFn: () => suppliersApi.getById(id),
    enabled: hydrated && isLoggedIn === true,
  });

  const updateMutation = useMutation({
    mutationFn: (data: SupplierUpdatePayload) => suppliersApi.update(id, data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['supplier', id], updated);
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => suppliersApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['suppliers'] });
      router.push('/suppliers');
    },
  });

  if (!hydrated || !isLoggedIn) return null;

  return (
    <div className="min-h-screen bg-off-white dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-light-gray dark:border-gray-700">
        <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Link
                href="/suppliers"
                className="inline-flex items-center gap-1.5 rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-600 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                Suppliers
              </Link>
              <h1 className="heading-2 text-primary-dark dark:text-primary-light">
                {isLoading ? 'Loading…' : (supplier?.name ?? 'Supplier')}
              </h1>
            </div>
            <AppNav />
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {isLoading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-light-gray dark:bg-gray-700 rounded-xl" />
            ))}
          </div>
        ) : !supplier ? (
          <div className="text-center py-16">
            <p className="body-text text-medium-gray dark:text-gray-400">Supplier not found.</p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Main card */}
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-6">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h2 className="text-xl font-semibold text-dark-gray dark:text-gray-100">
                    {supplier.name}
                  </h2>
                  <p className="text-sm text-medium-gray dark:text-gray-400 mt-0.5">
                    Added{' '}
                    {formatDistanceToNow(new Date(supplier.createdAt), { addSuffix: true })}
                  </p>
                </div>

                {!isEditing && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => setIsEditing(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-dark-gray dark:text-gray-200 border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 hover:bg-off-white dark:hover:bg-gray-600 transition-colors"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                      </svg>
                      Edit
                    </button>
                    <button
                      type="button"
                      onClick={() => setShowDeleteDialog(true)}
                      className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-red-600 dark:text-red-400 border border-red-200 dark:border-red-800 bg-white dark:bg-gray-700 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
                    >
                      <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                      </svg>
                      Delete
                    </button>
                  </div>
                )}
              </div>

              {isEditing ? (
                <>
                  {updateMutation.isError && (
                    <div className="mb-4 rounded-md bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 px-4 py-3 text-sm text-red-800 dark:text-red-300">
                      Failed to save changes. Please try again.
                    </div>
                  )}
                  <EditForm
                    supplier={supplier}
                    onSave={(data) => updateMutation.mutate(data)}
                    onCancel={() => { setIsEditing(false); updateMutation.reset(); }}
                    isPending={updateMutation.isPending}
                  />
                </>
              ) : (
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                  <DetailField label="Location" value={supplier.location} />
                  <DetailField label="City" value={supplier.city} />
                  <DetailField label="Country" value={supplier.country} />
                  <DetailField label="Region" value={supplier.region} />
                  <div className="sm:col-span-2">
                    <DetailField label="Commodities" value={supplier.commodities} />
                  </div>
                  {supplier.latestRiskLevel && (
                    <div className="sm:col-span-2">
                      <dt className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider mb-1">
                        Latest risk level
                      </dt>
                      <dd>
                        <span
                          className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${swarmLevelBadgeClasses[supplier.latestRiskLevel] ?? 'bg-light-gray/50 text-dark-gray'}`}
                        >
                          {supplier.latestRiskLevel}
                        </span>
                        {supplier.latestRiskScore != null && (
                          <span className="ml-2 text-sm text-medium-gray dark:text-gray-400">
                            Score: {supplier.latestRiskScore}
                          </span>
                        )}
                      </dd>
                    </div>
                  )}
                </dl>
              )}
            </div>

            {/* Risk summary card */}
            {!isEditing && (
              <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-6">
                <h3 className="text-sm font-semibold text-dark-gray dark:text-gray-200 uppercase tracking-wider mb-4">
                  Risk summary
                </h3>
                {supplier.riskSummary.count === 0 ? (
                  <p className="text-sm text-medium-gray dark:text-gray-400">No risks detected.</p>
                ) : (
                  <div className="space-y-3">
                    <p className="text-sm font-medium text-dark-gray dark:text-gray-200">
                      {supplier.riskSummary.count} risk{supplier.riskSummary.count !== 1 ? 's' : ''} detected
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(supplier.riskSummary.bySeverity)
                        .filter(([, n]) => n > 0)
                        .map(([sev, count]) => (
                          <span
                            key={sev}
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-medium ${severityBadgeClasses[sev] ?? 'bg-light-gray/50 text-dark-gray'}`}
                          >
                            {sev}: {count}
                          </span>
                        ))}
                    </div>
                    {supplier.riskSummary.latest && (
                      <p className="text-xs text-medium-gray dark:text-gray-400">
                        Latest: {supplier.riskSummary.latest.title}
                      </p>
                    )}
                  </div>
                )}

                {supplier.swarm && (
                  <div className="mt-6 pt-4 border-t border-light-gray dark:border-gray-700">
                    <h4 className="text-xs font-semibold text-dark-gray dark:text-gray-300 uppercase tracking-wider mb-3">
                      AI swarm analysis
                    </h4>
                    <div className="flex items-center gap-3 mb-3">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-lg text-xs font-semibold ${swarmLevelBadgeClasses[supplier.swarm.riskLevel] ?? 'bg-light-gray/50 text-dark-gray'}`}
                      >
                        {supplier.swarm.riskLevel}
                      </span>
                      <span className="text-xs text-medium-gray dark:text-gray-400">
                        Final score: {supplier.swarm.finalScore}
                      </span>
                    </div>
                    {supplier.swarm.topDrivers.length > 0 && (
                      <div className="mb-3">
                        <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-1">
                          Top drivers
                        </p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {supplier.swarm.topDrivers.map((d) => (
                            <li key={d} className="text-xs text-dark-gray dark:text-gray-300">
                              {d}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {supplier.swarm.mitigationPlan.length > 0 && (
                      <div>
                        <p className="text-xs font-medium text-medium-gray dark:text-gray-400 mb-1">
                          Suggested mitigations
                        </p>
                        <ul className="list-disc list-inside space-y-0.5">
                          {supplier.swarm.mitigationPlan.map((m) => (
                            <li key={m} className="text-xs text-dark-gray dark:text-gray-300">
                              {m}
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      {showDeleteDialog && supplier && (
        <DeleteConfirmDialog
          supplierName={supplier.name}
          onConfirm={() => deleteMutation.mutate()}
          onCancel={() => setShowDeleteDialog(false)}
          isPending={deleteMutation.isPending}
        />
      )}
    </div>
  );
}

function DetailField({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <dt className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wider mb-0.5">
        {label}
      </dt>
      <dd className="text-sm text-dark-gray dark:text-gray-200">
        {value || <span className="text-medium-gray dark:text-gray-500">—</span>}
      </dd>
    </div>
  );
}
