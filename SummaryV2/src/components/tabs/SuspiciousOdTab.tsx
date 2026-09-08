"use client";

import React, { useMemo, useState } from "react";
import { SurveyRecord } from "@/lib/types";
import { AlertTriangle, Download, ChevronDown, ChevronRight } from "lucide-react";

interface SuspiciousOdTabProps {
  records: SurveyRecord[];
}

function exportCsv(data: SurveyRecord[], filename: string) {
  if (!data || data.length === 0) return;
  const headers = [
    "Date", "Start Time", "End Time", "Surveyor", "Contact", "Survey Type",
    "Direction", "Vehicle Type", "Occupancy", "Origin", "Destination",
    "Duration (mins)", "Sample Quality Flags"
  ];

  const csvRows = [headers.join(",")];
  for (const r of data) {
    const row = [
      r.date || "",
      r.start_time || "",
      r.end_time || "",
      r.surveyor || "",
      r.contact || "",
      r.survey_type || "",
      r.direction || "",
      r.vehicle_type || "",
      r.occupancy || "",
      r.origin || "",
      r.destination || "",
      r.survey_duration_mins ?? "",
      r.sample_quality_flags || "",
    ].map((val) => `"${String(val).replace(/"/g, '""')}"`);
    csvRows.push(row.join(","));
  }

  const blob = new Blob([csvRows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.setAttribute("download", filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export const SuspiciousOdTab: React.FC<SuspiciousOdTabProps> = ({ records }) => {
  const suspiciousRecords = useMemo(
    () => records.filter((r) => r.sample_quality_suspicious),
    [records]
  );

  const totalFiltered = records.length;
  const suspiciousCount = suspiciousRecords.length;
  const suspiciousPct = totalFiltered > 0 ? ((suspiciousCount / totalFiltered) * 100).toFixed(1) : "0.0";

  // 6 Categorized Subsets matching app-2.py
  const categories = useMemo(() => {
    return [
      {
        title: "1. Origin: Delhi / New Delhi without locality",
        filename: "origin_delhi_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("origin delhi/new delhi without locality")
        ),
      },
      {
        title: "2. Destination: Delhi / New Delhi without locality",
        filename: "destination_delhi_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("destination delhi/new delhi without locality")
        ),
      },
      {
        title: "3. Origin: Gurugram/Gurgaon without sector/locality",
        filename: "origin_gurugram_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("origin gurugram/gurgaon without sector/locality")
        ),
      },
      {
        title: "4. Destination: Gurugram/Gurgaon without sector/locality",
        filename: "destination_gurugram_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("destination gurugram/gurgaon without sector/locality")
        ),
      },
      {
        title: "5. Origin: Noida without sector/locality",
        filename: "origin_noida_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("origin noida without sector/locality")
        ),
      },
      {
        title: "6. Destination: Noida without sector/locality",
        filename: "destination_noida_without_locality.csv",
        records: suspiciousRecords.filter((r) =>
          (r.sample_quality_flags || "").toLowerCase().includes("destination noida without sector/locality")
        ),
      },
    ];
  }, [suspiciousRecords]);

  const [expandedAll, setExpandedAll] = useState(false);

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      {/* Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">🚩 Suspicious OD Records</h2>
        <p className="text-xs text-slate-500">
          Entries where Delhi, New Delhi, Gurugram/Gurgaon, or Noida were submitted without adequate locality/sector detail
        </p>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-slate-500">Filtered Records</div>
          <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {totalFiltered.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
          <div className="text-xs font-medium text-rose-700 dark:text-rose-300">Suspicious OD Records</div>
          <div className="mt-1 text-2xl font-bold text-rose-900 dark:text-rose-100">
            {suspiciousCount.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
          <div className="text-xs font-medium text-rose-700 dark:text-rose-300">Suspicious OD %</div>
          <div className="mt-1 text-2xl font-bold text-rose-900 dark:text-rose-100">
            {suspiciousPct}%
          </div>
        </div>
      </div>

      <hr className="border-slate-200 dark:border-slate-800" />

      {/* 6 Category Tables */}
      <div className="space-y-4">
        {categories.map((cat, idx) => (
          <div
            key={`cat-${idx}`}
            className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200">
                  {cat.title} ({cat.records.length} records)
                </h3>
              </div>
              {cat.records.length > 0 && (
                <button
                  onClick={() => exportCsv(cat.records, cat.filename)}
                  className="flex items-center gap-1.5 rounded bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
                >
                  <Download className="h-3 w-3" />
                  <span>Download CSV</span>
                </button>
              )}
            </div>

            {cat.records.length === 0 ? (
              <div className="p-4 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                ✅ No suspicious records found for this category.
              </div>
            ) : (
              <div className="max-h-60 overflow-auto">
                <table className="w-full text-left text-xs">
                  <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                    <tr>
                      <th className="p-2">Date</th>
                      <th className="p-2">Time</th>
                      <th className="p-2">Surveyor</th>
                      <th className="p-2">Origin</th>
                      <th className="p-2">Destination</th>
                      <th className="p-2">Flags</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {cat.records.slice(0, 100).map((r, rIdx) => (
                      <tr key={`r-${rIdx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                        <td className="p-2 font-mono">{r.date}</td>
                        <td className="p-2 font-mono">{r.start_time}</td>
                        <td className="p-2 font-semibold">{r.surveyor}</td>
                        <td className="p-2 font-bold text-rose-700 dark:text-rose-300">{r.origin}</td>
                        <td className="p-2 font-bold text-rose-700 dark:text-rose-300">{r.destination}</td>
                        <td className="p-2 text-slate-500">{r.sample_quality_flags}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Show All Expander */}
      <div className="rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <button
          onClick={() => setExpandedAll(!expandedAll)}
          className="flex w-full items-center justify-between p-3.5 text-left text-xs font-bold text-slate-800 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-800/50"
        >
          <div className="flex items-center gap-2">
            {expandedAll ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
            <span>Show all suspicious OD records ({suspiciousCount} records)</span>
          </div>
          {suspiciousCount > 0 && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                exportCsv(suspiciousRecords, "all_suspicious_od_records.csv");
              }}
              className="flex items-center gap-1.5 rounded bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
            >
              <Download className="h-3 w-3" />
              <span>Download All CSV</span>
            </button>
          )}
        </button>

        {expandedAll && (
          <div className="max-h-96 overflow-auto border-t border-slate-200 p-2 dark:border-slate-800">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                <tr>
                  <th className="p-2">Date</th>
                  <th className="p-2">Time</th>
                  <th className="p-2">Surveyor</th>
                  <th className="p-2">Type</th>
                  <th className="p-2">Vehicle</th>
                  <th className="p-2">Origin</th>
                  <th className="p-2">Destination</th>
                  <th className="p-2">Quality Flags</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {suspiciousRecords.map((r, idx) => (
                  <tr key={`susp-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="p-2 font-mono">{r.date}</td>
                    <td className="p-2 font-mono">{r.start_time}</td>
                    <td className="p-2 font-semibold">{r.surveyor}</td>
                    <td className="p-2">{r.survey_type}</td>
                    <td className="p-2">{r.vehicle_type}</td>
                    <td className="p-2 font-bold text-rose-700 dark:text-rose-300">{r.origin}</td>
                    <td className="p-2 font-bold text-rose-700 dark:text-rose-300">{r.destination}</td>
                    <td className="p-2 text-rose-600">{r.sample_quality_flags}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

