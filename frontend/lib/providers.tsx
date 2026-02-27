'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ReactNode, useState } from 'react';
import { AuthProvider } from '@/lib/auth-context';
import { ThemeProvider } from '@/lib/theme-context';
import { RequireAuth } from '@/components/RequireAuth';

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            refetchOnWindowFocus: false,
            refetchInterval: 30000, // Refetch every 30 seconds
            staleTime: 10000, // Consider data stale after 10 seconds
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <RequireAuth>{children}</RequireAuth>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}
