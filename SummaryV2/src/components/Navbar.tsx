"use client";

import React, { useState } from "react";
import { RefreshCw, CloudDownload } from "lucide-react";

export type TabType =
  | "summary"
  | "surveyors"
  | "vehicles"
  | "suspicious"
  | "shift_purpose"
  | "raw_data"
  | "output";

interface NavbarProps {
  activeTab: TabType;
  onTabChange: (tab: TabType) => void;
  lastSyncedAt: string;
  onRefresh: () => void;
  onSyncTrafficLenz: () => Promise<void>;
  isLoading: boolean;
  isSyncing: boolean;
}

const TABS: { id: TabType; label: string }[] = [
  { id: "summary", label: "📊 Summary" },
  { id: "surveyors", label: "👷 Surveyors" },
  { id: "vehicles", label: "🚗 Vehicles" },
  { id: "suspicious", label: "🚩 Suspicious OD" },
  { id: "shift_purpose", label: "🔁 Shift / Frequency / Purpose" },
  { id: "raw_data", label: "📄 Raw Data" },
  { id: "output", label: "🗺️ Output" },
];

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  onTabChange,
  lastSyncedAt,
  onRefresh,
  onSyncTrafficLenz,
  isLoading,
  isSyncing,
}) => {
  const [formattedTime, setFormattedTime] = useState<string>("Just now");

  React.useEffect(() => {
    if (!lastSyncedAt) return;
    try {
      const date = new Date(lastSyncedAt);
      setFormattedTime(
        date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })
      );
    } catch {
      setFormattedTime("Just now");
    }
  }, [lastSyncedAt]);

  return (
    <header className="sticky top-0 z-30 flex flex-col border-b border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-900/95">
      {/* Top Banner Row */}
      <div className="flex h-14 w-full items-center justify-between px-4 sm:px-6">
        {/* Brand */}
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-200 dark:shadow-none">
            <span className="text-lg">🚦</span>
          </div>
          <div>
            <h1 className="text-sm font-bold text-slate-900 dark:text-white sm:text-base">
              Delhi OD Survey Dashboard <span className="rounded bg-indigo-100 px-1.5 py-0.5 text-[10px] font-semibold text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">v2.0 Next.js</span>
            </h1>
            <p className="text-[11px] text-slate-500">TrafficLenz Cloud Sync & High-Performance Data Grid</p>
          </div>
        </div>

        {/* Sync Controls */}
        <div className="flex items-center gap-2 sm:gap-3">
          {/* DB Synced Badge */}
          <div className="flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50/80 px-2.5 py-1 text-xs text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/40 dark:text-emerald-300">
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex h-2 w-2 rounded-full bg-emerald-500"></span>
            </span>
            <span className="hidden font-medium sm:inline">DB Synced:</span>
            <span>{formattedTime}</span>
          </div>

          {/* Sync Button */}
          <button
            onClick={onSyncTrafficLenz}
            disabled={isSyncing || isLoading}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:bg-indigo-700 disabled:opacity-50"
            title="Download the latest Excel from TrafficLenz portal"
          >
            <CloudDownload className={`h-3.5 w-3.5 ${isSyncing ? "animate-bounce" : ""}`} />
            <span className="hidden sm:inline">{isSyncing ? "Fetching..." : "Sync TrafficLenz"}</span>
          </button>

          {/* Refresh Button */}
          <button
            onClick={onRefresh}
            disabled={isLoading || isSyncing}
            className="flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"
            title="Refresh current data from database"
          >
            <RefreshCw className={`h-3 w-3 ${isLoading ? "animate-spin text-indigo-600" : ""}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>
      </div>

      {/* 7 Tabs Navigation Ribbon */}
      <div className="flex overflow-x-auto border-t border-slate-100 px-4 py-1.5 dark:border-slate-800/80 sm:px-6">
        <nav className="flex items-center gap-1.5">
          {TABS.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onTabChange(tab.id)}
                className={`flex whitespace-nowrap items-center gap-1 rounded-lg px-3 py-1.5 text-xs font-semibold transition ${
                  isActive
                    ? "bg-indigo-600 text-white shadow-sm shadow-indigo-200 dark:shadow-none"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                }`}
              >
                <span>{tab.label}</span>
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
};
