"use client";

import Link from "next/link";
import { BackendStatus } from "@/components/BackendStatus";

export function Nav() {
  return (
    <nav className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-900">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-6 px-4">
        <div className="flex items-center gap-6">
          <Link
            href="/"
            className="font-semibold text-zinc-900 dark:text-zinc-100"
          >
            Mock Server Dashboard
          </Link>
          <Link
            href="/"
            className="text-sm text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
          >
            Collections
          </Link>
        </div>
        <BackendStatus />
      </div>
    </nav>
  );
}
