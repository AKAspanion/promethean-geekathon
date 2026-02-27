'use client';

import { useEffect, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

const PUBLIC_PATHS = ['/login'];

export function RequireAuth({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { token, hydrated } = useAuth();

  const isPublic = pathname != null && PUBLIC_PATHS.some((p) => pathname === p);

  useEffect(() => {
    if (!hydrated) return;
    if (isPublic) return;
    if (!token) {
      router.replace('/login');
    }
  }, [hydrated, token, isPublic, router]);

  if (!hydrated) {
    return null;
  }
  if (!isPublic && !token) {
    return null;
  }
  return <>{children}</>;
}
