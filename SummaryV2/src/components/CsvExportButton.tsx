"use client";

import React, { useState } from "react";
import { Download, Loader2 } from "lucide-react";
import { GlobalFilterState, SurveyRecord } from "@/lib/types";

interface CsvExportButtonProps {
  filters: GlobalFilterState;
  filteredCount: number;
}

export const CsvExportButton: React.FC<CsvExportButtonProps> = ({ filters, filteredCount }) => {
  const [isExporting, setIsExporting] = useState(false);

  const handleExportCsv = async () => {
    if (filteredCount === 0) return;
    setIsExporting(true);

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

      params.append("pageSize", "-1"); // Fetch all filtered rows for CSV

      const res = await fetch(`/api/survey-data?${params.toString()}`);
      if (!res.ok) throw new Error("Failed to fetch export data");

      const data = await res.json();
      const records: SurveyRecord[] = data.records || [];

      // Columns matching prepare_display() in app-2.py
      const headers = [
        "Date",
        "Start Time",
        "End Time",
        "Entry Duration (sec)",
        "Entry Duration",
        "Surveyor",
        "Contact",
        "Survey Type",
        "Direction",
        "Vehicle Type",
        "Occupancy",
        "Origin",
        "Destination",
        "Duration (mins)",
        "Sample Quality Flags",
      ];

      const rows = records.map((r) => [
        `"${r.date || ""}"`,
        `"${r.start_time || ""}"`,
        `"${r.end_time || ""}"`,
        `"${r.entry_duration_sec ?? 0}"`,
        `"${r.entry_duration_sec ? `${r.entry_duration_sec}s` : ""}"`,
        `"${(r.surveyor || "").replace(/"/g, '""')}"`,
        `"${(r.contact || "").replace(/"/g, '""')}"`,
        `"${(r.survey_type || "").replace(/"/g, '""')}"`,
        `"${(r.direction || "").replace(/"/g, '""')}"`,
        `"${(r.vehicle_type || "").replace(/"/g, '""')}"`,
        `"${r.occupancy ?? ""}"`,
        `"${(r.origin || "").replace(/"/g, '""')}"`,
        `"${(r.destination || "").replace(/"/g, '""')}"`,
        `"${r.survey_duration_mins ?? ""}"`,
        `"${(r.sample_quality_flags || "").replace(/"/g, '""')}"`,
      ]);

      const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map((e) => e.join(","))].join("\n");
      const encodedUri = encodeURI(csvContent);
      const link = document.createElement("a");
      const timestamp = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      link.setAttribute("href", encodedUri);
      link.setAttribute("download", `delhi_od_survey_filtered_${timestamp}.csv`);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err) {
      console.error("Export error:", err);
      alert("Failed to export CSV. Please try again.");
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <button
      onClick={handleExportCsv}
      disabled={isExporting || filteredCount === 0}
      className={`inline-flex items-center gap-2 rounded-lg bg-emerald-600 px-3.5 py-2 text-xs font-semibold text-white shadow-sm transition hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:ring-offset-1 disabled:opacity-50 disabled:cursor-not-allowed`}
    >
      {isExporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
      <span>Download Filtered Data CSV ({filteredCount.toLocaleString()})</span>
    </button>
  );
};

