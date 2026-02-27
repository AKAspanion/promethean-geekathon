'use client';

export default function NewsPage() {
  return (
    <>
      <div>
        <h2 className="heading-3 text-dark-gray dark:text-gray-200">
          News Agent
        </h2>
        <p className="body-text text-medium-gray dark:text-gray-400">
          Supply chain & logistics news · Coming soon
        </p>
      </div>
      <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-8 border border-light-gray dark:border-gray-600 border-dashed mt-6">
          <div className="flex flex-col items-center justify-center gap-4 text-center min-h-[240px]">
            <div className="rounded-full bg-sky-blue/40 dark:bg-gray-700/50 p-4">
              <svg
                className="h-10 w-10 text-primary-dark dark:text-primary-light"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 20H5a2 2 0 01-2-2V6a2 2 0 012-2h10a2 2 0 012 2v1m2 13a2 2 0 01-2-2V7m2 13a2 2 0 002-2V9a2 2 0 00-2-2h-2m-4-3H9M7 16h6M7 8h6v4H7V8z"
                />
              </svg>
            </div>
            <div>
              <h3 className="heading-3 text-dark-gray dark:text-gray-200">
                News Agent
              </h3>
              <p className="mt-1 body-text text-medium-gray dark:text-gray-400 max-w-sm">
                This section will show supply chain and logistics news powered by the News Agent.
              </p>
            </div>
          </div>
      </div>
    </>
  );
}
