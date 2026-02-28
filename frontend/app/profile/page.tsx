'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { oemsApi, type Oem, type OemUpdatePayload } from '@/lib/api';
import { AppNav } from '@/components/AppNav';
import { useAuth } from '@/lib/auth-context';
import { formatDistanceToNow } from 'date-fns';

interface EditFormState {
  name: string;
  email: string;
  location: string;
  city: string;
  country: string;
  countryCode: string;
  region: string;
  commodities: string;
}

function DeleteConfirmDialog({
  onConfirm,
  onCancel,
  isPending,
}: {
  onConfirm: () => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-800 rounded-xl shadow-xl border border-light-gray dark:border-gray-700 p-6 max-w-md w-full mx-4">
        <h3 className="text-lg font-semibold text-dark-gray dark:text-gray-100 mb-2">
          Delete account
        </h3>
        <p className="text-sm text-medium-gray dark:text-gray-400 mb-6">
          Are you sure you want to delete your account? This will permanently remove all your data
          including suppliers, risks, and analysis. This action cannot be undone.
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
            {isPending ? 'Deleting…' : 'Delete account'}
          </button>
        </div>
      </div>
    </div>
  );
}

function EditForm({
  profile,
  onSave,
  onCancel,
  isPending,
}: {
  profile: Oem;
  onSave: (data: OemUpdatePayload) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [form, setForm] = useState<EditFormState>({
    name: profile.name ?? '',
    email: profile.email ?? '',
    location: profile.location ?? '',
    city: profile.city ?? '',
    country: profile.country ?? '',
    countryCode: profile.countryCode ?? '',
    region: profile.region ?? '',
    commodities: profile.commodities ?? '',
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const payload: OemUpdatePayload = {};
    if (form.name) payload.name = form.name;
    if (form.email) payload.email = form.email;
    if (form.location) payload.location = form.location;
    if (form.city) payload.city = form.city;
    if (form.country) payload.country = form.country;
    if (form.countryCode) payload.countryCode = form.countryCode;
    if (form.region) payload.region = form.region;
    if (form.commodities) payload.commodities = form.commodities;
    onSave(payload);
  };

  const labelClass = 'block text-xs font-medium text-medium-gray dark:text-gray-400 mb-1';
  const inputClass =
    'w-full rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm text-dark-gray dark:text-gray-200 focus:outline-none focus:ring-2 focus:ring-primary-dark dark:focus:ring-primary-light';

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
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
          <label htmlFor="email" className={labelClass}>
            Email <span className="text-red-500">*</span>
          </label>
          <input
            id="email"
            name="email"
            type="email"
            required
            value={form.email}
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
          <label htmlFor="countryCode" className={labelClass}>
            Country Code
          </label>
          <input
            id="countryCode"
            name="countryCode"
            type="text"
            value={form.countryCode}
            onChange={handleChange}
            className={inputClass}
            placeholder="e.g. US, IN, DE"
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
        <div>
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
            placeholder="e.g. Semiconductor Chips, Steel"
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
          disabled={isPending || !form.name || !form.email}
          className="px-5 py-2 rounded-lg text-sm font-semibold text-white bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? 'Saving…' : 'Save changes'}
        </button>
      </div>
    </form>
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

export default function ProfilePage() {
  const router = useRouter();
  const { isLoggedIn, hydrated, logout, updateOem } = useAuth();
  const queryClient = useQueryClient();
  const [isEditing, setIsEditing] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  const { data: profile, isLoading } = useQuery({
    queryKey: ['oem-profile'],
    queryFn: () => oemsApi.getProfile(),
    enabled: hydrated && isLoggedIn === true,
  });

  const updateMutation = useMutation({
    mutationFn: (data: OemUpdatePayload) => oemsApi.updateProfile(data),
    onSuccess: (updated) => {
      queryClient.setQueryData(['oem-profile'], updated);
      updateOem(updated);
      setIsEditing(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => oemsApi.deleteAccount(),
    onSuccess: () => {
      logout();
      router.push('/login');
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
                href="/"
                className="inline-flex items-center gap-1.5 rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 px-3 py-2 text-sm font-medium text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-600 transition-colors"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden>
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
                </svg>
                Dashboard
              </Link>
              <h1 className="heading-2 text-primary-dark dark:text-primary-light">
                Profile
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
        ) : !profile ? (
          <div className="text-center py-16">
            <p className="body-text text-medium-gray dark:text-gray-400">Profile not found.</p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-6">
              <div className="flex items-start justify-between mb-6">
                <div>
                  <h2 className="text-xl font-semibold text-dark-gray dark:text-gray-100">
                    {profile.name}
                  </h2>
                  <p className="text-sm text-medium-gray dark:text-gray-400 mt-0.5">
                    Member since{' '}
                    {formatDistanceToNow(new Date(profile.createdAt), { addSuffix: true })}
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
                    profile={profile}
                    onSave={(data) => updateMutation.mutate(data)}
                    onCancel={() => { setIsEditing(false); updateMutation.reset(); }}
                    isPending={updateMutation.isPending}
                  />
                </>
              ) : (
                <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">
                  <DetailField label="Email" value={profile.email} />
                  <DetailField label="Location" value={profile.location} />
                  <DetailField label="City" value={profile.city} />
                  <DetailField label="Country" value={profile.country} />
                  <DetailField label="Country Code" value={profile.countryCode} />
                  <DetailField label="Region" value={profile.region} />
                  <div className="sm:col-span-2">
                    <DetailField label="Commodities" value={profile.commodities} />
                  </div>
                </dl>
              )}
            </div>
          </div>
        )}
      </main>

      {showDeleteDialog && (
        <DeleteConfirmDialog
          onConfirm={() => deleteMutation.mutate()}
          onCancel={() => setShowDeleteDialog(false)}
          isPending={deleteMutation.isPending}
        />
      )}
    </div>
  );
}
