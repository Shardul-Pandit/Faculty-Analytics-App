"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { BarChart3, Upload, LayoutDashboard, LogOut } from "lucide-react";
import { clearSession, getUser } from "@/lib/auth";
import { clsx } from "clsx";

const NAV = [
  { href: "/dashboard", label: "Dashboard",  icon: LayoutDashboard },
  { href: "/upload",    label: "Upload Data", icon: Upload },
];

export default function NavBar() {
  const router   = useRouter();
  const pathname = usePathname();

  // Read from localStorage only after mount to avoid server/client hydration mismatch
  const [username, setUsername] = useState<string | null>(null);
  useEffect(() => {
    setUsername(getUser()?.username ?? null);
  }, []);

  function signOut() {
    clearSession();
    router.push("/login");
  }

  return (
    <header className="sticky top-0 z-30 border-b border-gray-200 bg-white">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-4">

        {/* Brand */}
        <Link href="/dashboard" className="flex items-center gap-2">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
            <BarChart3 className="h-4 w-4 text-white" />
          </div>
          <span className="font-semibold text-gray-900">Faculty Analytics</span>
        </Link>

        {/* Nav links */}
        <nav className="flex items-center gap-1">
          {NAV.map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                pathname.startsWith(href)
                  ? "bg-indigo-50 text-indigo-700"
                  : "text-gray-600 hover:bg-gray-100"
              )}
            >
              <Icon className="h-4 w-4" />
              {label}
            </Link>
          ))}
        </nav>

        {/* User + sign out */}
        <div className="flex items-center gap-3">
          {username && (
            <span className="text-sm text-gray-500 hidden sm:block">
              {username}
            </span>
          )}
          <button
            onClick={signOut}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-100 transition-colors"
          >
            <LogOut className="h-4 w-4" />
            Sign out
          </button>
        </div>

      </div>
    </header>
  );
}
