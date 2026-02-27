"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AppNav } from "@/components/AppNav";

export function AppHeader() {
  const pathname = usePathname();

  const navLinks = [
    { href: "/", label: "Dashboard" },
    { href: "/weather-risk", label: "Weather" },
    { href: "/shipping-risk", label: "Shipment" },
    { href: "/news-risk", label: "News" },
  ];

  return (
    <header className="bg-white dark:bg-gray-800 shadow-sm border-b border-light-gray dark:border-gray-700">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h1 className="heading-2 text-primary-dark dark:text-primary-light">
              Predictive Supply Chain Agent
            </h1>
            <p className="body-text text-medium-gray dark:text-gray-400 text-base">
              Global Watchtower for Manufacturing Logistics
            </p>
          </div>
          <div className="flex items-center gap-4">
            <div className="flex gap-1 rounded-lg border border-light-gray dark:border-gray-600 bg-sky-blue/30 dark:bg-gray-700/50 p-1">
              {navLinks.map(({ href, label }) => {
                const isActive =
                  href === "/" ? pathname === "/" : pathname?.startsWith(href);
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`rounded-lg px-3 py-2 text-sm font-medium transition ${
                      isActive
                        ? "bg-primary-dark text-white shadow"
                        : "text-dark-gray dark:text-gray-300 hover:bg-primary-dark/10 dark:hover:bg-gray-600 hover:text-primary-dark dark:hover:text-primary-light"
                    }`}
                  >
                    {label}
                  </Link>
                );
              })}
            </div>
            <AppNav />
          </div>
        </div>
      </div>
    </header>
  );
}
