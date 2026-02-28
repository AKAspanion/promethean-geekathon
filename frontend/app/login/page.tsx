"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation } from "@tanstack/react-query";
import { oemsApi } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { AppNav } from "@/components/AppNav";

export default function LoginPage() {
  const router = useRouter();
  const { login } = useAuth();
  const [email, setEmail] = useState("");

  const loginMutation = useMutation({
    mutationFn: (emailAddress: string) => oemsApi.login(emailAddress),
    onSuccess: (data) => {
      login(data.token, data.oem);
      router.push("/");
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = email.trim();
    if (!trimmed) return;
    loginMutation.mutate(trimmed);
  };

  return (
    <div className="min-h-screen bg-off-white dark:bg-gray-900">
      <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-light-gray dark:border-gray-700">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex items-center justify-between">
            <h1 className="heading-3 text-primary-dark dark:text-primary-light">
              OEM Login
            </h1>
            <AppNav />
          </div>
        </div>
      </header>

      <main className="max-w-md mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm border border-light-gray dark:border-gray-700 p-8">
          <p className="body-text text-medium-gray dark:text-gray-400 mb-6">
            Sign in with your email. No password required. If you don’t have an
            account, we’ll create one.
          </p>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="block text-sm font-medium text-dark-gray dark:text-gray-200 mb-1"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                required
                className="w-full px-3 py-2 rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-700 text-dark-gray dark:text-gray-100 placeholder-medium-gray dark:placeholder-gray-400 focus:ring-2 focus:ring-primary-light focus:border-transparent"
              />
            </div>
            <button
              type="submit"
              disabled={loginMutation.isPending}
              className="w-full px-5 py-2.5 rounded-lg bg-primary-dark hover:bg-primary-light disabled:bg-light-gray dark:disabled:bg-gray-600 disabled:cursor-not-allowed text-white font-medium transition-colors text-base"
            >
              {loginMutation.isPending ? "Signing in..." : "Sign in"}
            </button>
          </form>
          {loginMutation.isError && (
            <p className="mt-4 text-sm text-red-600 dark:text-red-400">
              {loginMutation.error instanceof Error
                ? loginMutation.error.message
                : "Sign in failed"}
            </p>
          )}
          <p className="mt-6 body-text text-medium-gray dark:text-gray-400 text-center">
            New here? Sign in with your email to create an account.
          </p>
        </div>
      </main>
    </div>
  );
}
