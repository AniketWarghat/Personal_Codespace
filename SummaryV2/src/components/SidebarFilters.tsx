"use client";

import React from "react";
import { Filter, Calendar, Clock, RotateCcw } from "lucide-react";
import { GlobalFilterState, FilterOptionsResponse } from "@/lib/types";
import { MultiSelectDropdown } from "./MultiSelectDropdown";

interface SidebarFiltersProps {
  filterOptions: FilterOptionsResponse | null;
  filters: GlobalFilterState;
  onFilterChange: (filters: GlobalFilterState) => void;
  filteredCount: number;
  totalCount: number;
  isLoading: boolean;
}

// 15-minute time slots (00:00 to 23:45)
const TIME_SLOTS: string[] = [];
for (let h = 0; h < 24; h++) {
  for (let m = 0; m < 60; m += 15) {
    const hh = String(h).padStart(2, "0");
    const mm = String(m).padStart(2, "0");
    TIME_SLOTS.push(`${hh}:${mm}`);
  }
}

export const SidebarFilters: React.FC<SidebarFiltersProps> = ({
  filterOptions,
  filters,
  onFilterChange,
  filteredCount,
  totalCount,
  isLoading,
}) => {
  const handleResetFilters = () => {
    if (!filterOptions) return;
    onFilterChange({
      dateFrom: filterOptions.minDate || "",
      dateTo: filterOptions.maxDate || "",
      timeFrom: "00:00",
      timeTo: "23:45",
      surveyTypes: [...filterOptions.surveyTypes],
      directions: [...filterOptions.directions],
      vehicleTypes: [...filterOptions.vehicleTypes],
      surveyors: [...filterOptions.surveyors],
    });
  };

  const percentage = totalCount > 0 ? ((filteredCount / totalCount) * 100).toFixed(1) : "0";

  return (
    <aside className="flex h-full w-80 flex-col border-r border-slate-200 bg-slate-50/70 dark:border-slate-800 dark:bg-slate-950/70">
      {/* Header & Metrics */}
      <div className="border-b border-slate-200 p-4 dark:border-slate-800">
        <div className="flex items-center justify-between pb-3">
          <div className="flex items-center gap-2 font-semibold text-slate-800 dark:text-slate-100">
            <Filter className="h-4 w-4 text-indigo-600 dark:text-indigo-400" />
            <span>Global Filters</span>
          </div>
          <button
            onClick={handleResetFilters}
            className="flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-500 transition hover:bg-slate-200/60 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-200"
            title="Reset to default filters"
          >
            <RotateCcw className="h-3 w-3" />
            <span>Reset</span>
          </button>
        </div>

        {/* Filtered Records Metric Widget (Mirrors Streamlit sidebar metric) */}
        <div className="rounded-xl border border-indigo-100 bg-indigo-50/70 p-3 dark:border-indigo-900/50 dark:bg-indigo-950/30">
          <div className="text-xs font-medium text-indigo-700 dark:text-indigo-300">
            Filtered Records
          </div>
          <div className="flex items-baseline gap-2 pt-1">
            <span className="text-2xl font-bold tracking-tight text-indigo-900 dark:text-indigo-100">
              {filteredCount.toLocaleString()}
            </span>
            <span className="text-xs text-indigo-600/80 dark:text-indigo-400">
              of {totalCount.toLocaleString()} ({percentage}%)
            </span>
          </div>
        </div>
      </div>

      {/* Filter Controls Scrollable Body */}
      <div className="flex-1 space-y-5 overflow-y-auto p-4">
        {/* 1. Date Range */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Calendar className="h-3.5 w-3.5" />
            <span>Date Range</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] text-slate-500">From</label>
              <input
                type="date"
                value={filters.dateFrom || ""}
                max={filters.dateTo || undefined}
                onChange={(e) => onFilterChange({ ...filters, dateFrom: e.target.value })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              />
            </div>
            <div>
              <label className="text-[11px] text-slate-500">To</label>
              <input
                type="date"
                value={filters.dateTo || ""}
                min={filters.dateFrom || undefined}
                onChange={(e) => onFilterChange({ ...filters, dateTo: e.target.value })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              />
            </div>
          </div>
        </div>

        {/* 2. Survey Start Time Range (15-min increments) */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-slate-500">
            <Clock className="h-3.5 w-3.5" />
            <span>Survey Start Time</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="text-[11px] text-slate-500">From</label>
              <select
                value={filters.timeFrom || "00:00"}
                onChange={(e) => onFilterChange({ ...filters, timeFrom: e.target.value })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              >
                {TIME_SLOTS.map((t) => (
                  <option key={`from-${t}`} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-[11px] text-slate-500">To</label>
              <select
                value={filters.timeTo || "23:45"}
                onChange={(e) => onFilterChange({ ...filters, timeTo: e.target.value })}
                className="w-full rounded-md border border-slate-300 bg-white px-2 py-1.5 text-xs text-slate-800 shadow-sm focus:border-indigo-500 focus:outline-none dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
              >
                {TIME_SLOTS.map((t) => (
                  <option key={`to-${t}`} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        <hr className="border-slate-200 dark:border-slate-800" />

        {/* 3. Survey Type */}
        <MultiSelectDropdown
          label="Survey Type"
          options={filterOptions?.surveyTypes || []}
          selected={filters.surveyTypes}
          onChange={(selected) => onFilterChange({ ...filters, surveyTypes: selected })}
        />

        {/* 4. Direction / Arm */}
        <MultiSelectDropdown
          label="Direction / Arm"
          options={filterOptions?.directions || []}
          selected={filters.directions}
          onChange={(selected) => onFilterChange({ ...filters, directions: selected })}
        />

        {/* 5. Vehicle Type */}
        <MultiSelectDropdown
          label="Vehicle Type"
          options={filterOptions?.vehicleTypes || []}
          selected={filters.vehicleTypes}
          onChange={(selected) => onFilterChange({ ...filters, vehicleTypes: selected })}
        />

        {/* 6. Surveyor */}
        <MultiSelectDropdown
          label="Surveyor"
          options={filterOptions?.surveyors || []}
          selected={filters.surveyors}
          onChange={(selected) => onFilterChange({ ...filters, surveyors: selected })}
        />
      </div>
    </aside>
  );
};

