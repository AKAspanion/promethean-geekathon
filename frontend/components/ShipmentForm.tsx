"use client";

interface ShipmentFormProps {
  onSubmit: (e: React.FormEvent) => void;
  loading: boolean;
  error: string | null;
}

export function ShipmentForm({ onSubmit, loading, error }: ShipmentFormProps) {
  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-[20px] font-semibold leading-tight text-dark-gray dark:text-gray-200">
            Shipment Weather Analysis
          </h2>
          <p className="mt-1 text-[13px] text-medium-gray dark:text-gray-400">
            Supplier and OEM cities are resolved automatically from your account.
          </p>
        </div>
        <span className="rounded-full border border-sky-blue dark:border-primary-light/50 bg-sky-blue/30 dark:bg-gray-700/50 px-3 py-1 text-[12px] font-medium text-primary-dark dark:text-primary-light">
          Supplier → OEM · Weather Exposure
        </span>
      </div>

      <button
        type="submit"
        disabled={loading}
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-dark px-5 py-3 text-[16px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-primary-light dark:text-gray-900 dark:hover:opacity-90"
      >
        {loading ? (
          <>
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
              aria-hidden
            />
            Analysing shipment weather exposure…
          </>
        ) : (
          "Run Shipment Weather Analysis"
        )}
      </button>

      {error && (
        <p className="text-[14px] text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}
    </form>
  );
}
