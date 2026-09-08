"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Navbar, TabType } from "@/components/Navbar";
import { SidebarFilters } from "@/components/SidebarFilters";
import { RawDataTable } from "@/components/RawDataTable";
import { CsvExportButton } from "@/components/CsvExportButton";
import { GlobalFilterState, FilterOptionsResponse, SurveyRecord } from "@/lib/types";
import { SummaryTab } from "@/components/tabs/SummaryTab";
import { SurveyorsTab } from "@/components/tabs/SurveyorsTab";
import { VehiclesTab } from "@/components/tabs/VehiclesTab";
import { SuspiciousOdTab } from "@/components/tabs/SuspiciousOdTab";
import { ShiftPurposeTab } from "@/components/tabs/ShiftPurposeTab";
import { OutputTab } from "@/components/tabs/OutputTab";
import { Table } from "lucide-react";

export default function Home() {
  const [activeTab, setActiveTab] = useState<TabType>("summary");
  const [filterOptions, setFilterOptions] = useState<FilterOptionsResponse | null>(null);
  const [filters, setFilters] = useState<GlobalFilterState>({
    dateFrom: "",
    dateTo: "",
    timeFrom: "00:00",
    timeTo: "23:45",
    surveyTypes: [],
    directions: [],
    vehicleTypes: [],
    surveyors: [],
  });

  const [records, setRecords] = useState<SurveyRecord[]>([]);
  const [allFilteredRecords, setAllFilteredRecords] = useState<SurveyRecord[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [filteredCount, setFilteredCount] = useState(0);
  const [lastSyncedAt, setLastSyncedAt] = useState<string>("");

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [sortBy, setSortBy] = useState("date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");

  const [isLoading, setIsLoading] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);

  // 1. Fetch distinct filter options on mount
  const loadOptions = useCallback(async () => {
    try {
      const res = await fetch("/api/filter-options");
      if (!res.ok) throw new Error("Failed to load options");
      const data: FilterOptionsResponse = await res.json();
      setFilterOptions(data);
      setLastSyncedAt(data.lastSyncedAt);

      if (!isInitialized) {
        setFilters({
          dateFrom: data.minDate || "",
          dateTo: data.maxDate || "",
          timeFrom: "00:00",
          timeTo: "23:45",
          surveyTypes: [...data.surveyTypes],
          directions: [...data.directions],
          vehicleTypes: [...data.vehicleTypes],
          surveyors: [...data.surveyors],
        });
        setIsInitialized(true);
      }
    } catch (err) {
      console.error("Failed to load filter options:", err);
      setIsInitialized(true);
    }
  }, [isInitialized]);

  useEffect(() => {
    loadOptions();
  }, [loadOptions]);

  // 2. Fetch survey data
  const fetchSurveyData = useCallback(async () => {
    if (!isInitialized) return;
    setIsLoading(true);

    try {
      const params = new URLSearchParams();
      if (filters.dateFrom) params.append("dateFrom", filters.dateFrom);
      if (filters.dateTo) params.append("dateTo", filters.dateTo);
      if (filters.timeFrom) params.append("timeFrom", filters.timeFrom);
      if (filters.timeTo) params.append("timeTo", filters.timeTo);

      filters.surveyTypes.forEach((s) => params.append("surveyType", s));
      filters.directions.forEach((d) => params.append("direction", d));
      filters.vehicleTypes.forEach((v) => params.append("vehicleType", v));
      filters.surveyors.forEach((s) => params.append("surveyor", s));

      params.append("page", page.toString());
      params.append("pageSize", pageSize.toString());
      params.append("sortBy", sortBy);
      params.append("sortOrder", sortOrder);

      const res = await fetch(`/api/survey-data?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to load survey records");
      const data = await res.json();

      setRecords(data.records || []);
      setAllFilteredRecords(data.records || []);
      setTotalCount(data.totalCount || 0);
      setFilteredCount(data.filteredCount || 0);
      if (data.lastSyncedAt) {
        setLastSyncedAt(data.lastSyncedAt);
      }
    } catch (err) {
      console.error("Error fetching survey records:", err);
    } finally {
      setIsLoading(false);
    }
  }, [filters, page, pageSize, sortBy, sortOrder, isInitialized]);

  useEffect(() => {
    fetchSurveyData();
  }, [fetchSurveyData]);

  // 3. Auto-refresh polling every 30 seconds
  useEffect(() => {
    const interval = setInterval(() => {
      fetchSurveyData();
    }, 30000);
    return () => clearInterval(interval);
  }, [fetchSurveyData]);

  // 4. Trigger direct TrafficLenz download and sync
  const handleSyncTrafficLenz = async () => {
    setIsSyncing(true);
    try {
      const res = await fetch("/api/sync", { method: "POST" });
      const data = await res.json();
      if (data.success) {
        await loadOptions();
        await fetchSurveyData();
      } else {
        alert(`Sync failed: ${data.error || "Unknown error"}`);
      }
    } catch (err: any) {
      alert(`Sync error: ${err.message || err}`);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleFilterChange = (newFilters: GlobalFilterState) => {
    setFilters(newFilters);
    setPage(1);
  };

  const handleSortChange = (newSortBy: string, newSortOrder: "asc" | "desc") => {
    setSortBy(newSortBy);
    setSortOrder(newSortOrder);
    setPage(1);
  };

  return (
    <div className="flex h-screen w-screen flex-col overflow-hidden bg-slate-100 dark:bg-slate-950">
      {/* Top Navbar with 7 Tabs */}
      <Navbar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        lastSyncedAt={lastSyncedAt}
        onRefresh={fetchSurveyData}
        onSyncTrafficLenz={handleSyncTrafficLenz}
        isLoading={isLoading}
        isSyncing={isSyncing}
      />

      {/* Main Container: Sidebar + Active Tab Content Area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Global Filters Sidebar */}
        <SidebarFilters
          filterOptions={filterOptions}
          filters={filters}
          onFilterChange={handleFilterChange}
          filteredCount={filteredCount}
          totalCount={totalCount}
          isLoading={isLoading}
        />

        {/* Tab Content Body */}
        <main className="flex flex-1 flex-col overflow-hidden">
          {/* TAB 1: 📊 Summary */}
          {activeTab === "summary" && (
            <SummaryTab records={allFilteredRecords} totalFiltered={filteredCount} />
          )}

          {/* TAB 2: 👷 Surveyors */}
          {activeTab === "surveyors" && <SurveyorsTab records={allFilteredRecords} />}

          {/* TAB 3: 🚗 Vehicles */}
          {activeTab === "vehicles" && <VehiclesTab records={allFilteredRecords} />}

          {/* TAB 4: 🚩 Suspicious OD */}
          {activeTab === "suspicious" && <SuspiciousOdTab records={allFilteredRecords} />}

          {/* TAB 5: 🔁 Shift / Frequency / Purpose */}
          {activeTab === "shift_purpose" && <ShiftPurposeTab records={allFilteredRecords} />}

          {/* TAB 6: 📄 Raw Data */}
          {activeTab === "raw_data" && (
            <div className="flex flex-1 flex-col overflow-hidden p-4">
              {/* Action Ribbon & Quick Stats */}
              <div className="mb-3 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="flex items-center gap-1.5 rounded-md bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm dark:bg-slate-900 dark:text-slate-200">
                    <Table className="h-3.5 w-3.5 text-indigo-600" />
                    <span>Raw Survey Records</span>
                  </span>
                  <span className="text-xs text-slate-500">
                    Displaying <b>{records.length}</b> records on page {page} of{" "}
                    {Math.ceil(filteredCount / pageSize) || 1}
                  </span>
                </div>

                <CsvExportButton filters={filters} filteredCount={filteredCount} />
              </div>

              {/* TanStack Table */}
              <div className="flex-1 overflow-hidden">
                <RawDataTable
                  records={records}
                  totalCount={totalCount}
                  filteredCount={filteredCount}
                  page={page}
                  pageSize={pageSize}
                  sortBy={sortBy}
                  sortOrder={sortOrder}
                  onPageChange={setPage}
                  onPageSizeChange={(newSize) => {
                    setPageSize(newSize);
                    setPage(1);
                  }}
                  onSortChange={handleSortChange}
                  isLoading={isLoading}
                />
              </div>
            </div>
          )}

          {/* TAB 7: 🗺️ Output */}
          {activeTab === "output" && <OutputTab records={allFilteredRecords} />}
        </main>
      </div>
    </div>
  );
}
