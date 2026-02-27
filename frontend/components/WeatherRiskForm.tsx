"use client";

interface WeatherRiskFormProps {
  city: string;
  onCityChange: (value: string) => void;
  onSubmit: (e: React.FormEvent) => void;
  loading: boolean;
  error: string | null;
}

export function WeatherRiskForm({
  city,
  onCityChange,
  onSubmit,
  loading,
  error,
}: WeatherRiskFormProps) {
  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-col gap-4 rounded-2xl border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 p-5 shadow-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-[20px] font-semibold leading-tight text-dark-gray dark:text-gray-200">
          Scenario input
        </h2>
        <span className="rounded-full border border-sky-blue dark:border-primary-light/50 bg-sky-blue/30 dark:bg-gray-700/50 px-3 py-1 text-[12px] font-medium text-primary-dark dark:text-primary-light">
          Live Weather · Agentic Flow
        </span>
      </div>
      <div>
        <label
          htmlFor="city-input"
          className="mb-1.5 block text-[14px] font-medium text-dark-gray dark:text-gray-200"
        >
          City
        </label>
        <input
          id="city-input"
          type="text"
          value={city}
          onChange={(e) => onCityChange(e.target.value)}
          placeholder="e.g. New Delhi, London, Mumbai"
          className="w-full rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-700 px-4 py-3 text-[16px] text-dark-gray dark:text-gray-100 outline-none transition placeholder:text-medium-gray dark:placeholder-gray-400 focus:border-primary-light focus:ring-2 focus:ring-primary-light/20"
          required
          disabled={loading}
        />
      </div>
      <button
        type="submit"
        disabled={loading}
        className="inline-flex items-center justify-center gap-2 rounded-lg bg-primary-dark px-5 py-3 text-[16px] font-semibold text-white shadow-sm transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {loading ? (
          <>
            <span
              className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent"
              aria-hidden
            />
            Running weather risk agent…
          </>
        ) : (
          "Run weather risk assessment"
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
