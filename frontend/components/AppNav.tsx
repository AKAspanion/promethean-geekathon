"use client";

import { useRef, useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/lib/auth-context";
import { useTheme } from "@/lib/theme-context";

export function AppNav() {
  const { isLoggedIn, oem, logout } = useAuth();
  const { theme, setTheme } = useTheme();
  const [profileOpen, setProfileOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setProfileOpen(false);
      }
    }
    if (profileOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [profileOpen]);

  const handleLogout = () => {
    setProfileOpen(false);
    logout();
  };

  const handleSuppliersClick = () => {
    setProfileOpen(false);
  };

  return (
    <nav className="flex items-center gap-6 text-sm font-medium">
      {isLoggedIn ? (
        <>
          <div className="relative" ref={menuRef}>
            <button
              type="button"
              onClick={() => setProfileOpen((prev) => !prev)}
              className="flex items-center gap-2 rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-800 px-3 py-2 text-dark-gray dark:text-gray-200 hover:bg-sky-blue/20 dark:hover:bg-gray-700 transition-colors"
              aria-expanded={profileOpen}
              aria-haspopup="true"
            >
              <span className="h-2 w-2 rounded-full bg-cyan-blue" aria-hidden />
              <span
                className="truncate max-w-40"
                title={oem?.name ?? oem?.email}
              >
                {oem?.name ?? "Profile"}
              </span>
              <svg
                className={`h-4 w-4 transition-transform ${profileOpen ? "rotate-180" : ""}`}
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                aria-hidden
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 9l-7 7-7-7"
                />
              </svg>
            </button>
            {profileOpen && (
              <div
                className="absolute right-0 top-full z-10 mt-1 min-w-50 rounded-lg border border-light-gray dark:border-gray-600 bg-white dark:bg-gray-800 py-1 shadow-lg"
                role="menu"
              >
                <Link
                  href="/profile"
                  onClick={() => setProfileOpen(false)}
                  className="block w-full px-3 py-2 text-left text-sm text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
                  role="menuitem"
                >
                  Profile
                </Link>
                <Link
                  href="/suppliers"
                  onClick={handleSuppliersClick}
                  className="block w-full px-3 py-2 text-left text-sm text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
                  role="menuitem"
                >
                  Suppliers
                </Link>
                <div className="border-b border-light-gray dark:border-gray-600 px-3 py-2 flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wide">
                    Theme
                  </span>
                  <div className="flex rounded-lg border border-light-gray dark:border-gray-600 bg-off-white dark:bg-gray-800 p-0.5">
                    <button
                      type="button"
                      onClick={() => setTheme("light")}
                      className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                        theme === "light"
                          ? "bg-white dark:bg-gray-700 text-primary-dark dark:text-primary-light shadow"
                          : "text-medium-gray dark:text-gray-400 hover:text-dark-gray dark:hover:text-gray-200"
                      }`}
                      aria-pressed={theme === "light"}
                    >
                      Light
                    </button>
                    <button
                      type="button"
                      onClick={() => setTheme("dark")}
                      className={`rounded-md px-2 py-1 text-xs font-medium transition ${
                        theme === "dark"
                          ? "bg-white dark:bg-gray-700 text-primary-dark dark:text-primary-light shadow"
                          : "text-medium-gray dark:text-gray-400 hover:text-dark-gray dark:hover:text-gray-200"
                      }`}
                      aria-pressed={theme === "dark"}
                    >
                      Dark
                    </button>
                  </div>
                </div>
                <div className="border-b border-light-gray dark:border-gray-600 px-3 py-2">
                  <p className="text-xs font-medium text-medium-gray dark:text-gray-400 uppercase tracking-wide">
                    Signed in as
                  </p>
                  <p
                    className="truncate text-sm font-medium text-dark-gray dark:text-gray-200"
                    title={oem?.email}
                  >
                    {oem?.email}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="w-full px-3 py-2 text-left text-sm text-dark-gray dark:text-gray-200 hover:bg-off-white dark:hover:bg-gray-700/50 transition-colors"
                  role="menuitem"
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </>
      ) : (
        <Link
          href="/login"
          className="rounded-lg px-4 py-2 bg-primary-dark text-white hover:bg-primary-light transition-colors"
        >
          Login
        </Link>
      )}
    </nav>
  );
}
