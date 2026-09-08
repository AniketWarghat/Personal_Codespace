"use client";

import React, { useState, useMemo } from "react";
import { SurveyRecord } from "@/lib/types";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { Download } from "lucide-react";

interface SurveyorsTabProps {
  records: SurveyRecord[];
}

const COLORS = ["#4f46e5", "#06b6d4", "#10b981", "#f59e0b", "#ec4899", "#8b5cf6", "#3b82f6", "#64748b"];

function formatSeconds(sec: number): string {
  if (sec <= 0 || isNaN(sec)) return "0s";
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  if (m === 0) return `${s}s`;
  return `${m}m ${s}s`;
}

function exportCsv(data: any[], filename: string) {
  if (!data || data.length === 0) return;
  const headers = Object.keys(data[0]);
  const csvRows = [headers.join(",")];
  for (const row of data) {
    const values = headers.map((h) => {
      const val = row[h] ?? "";
      return `"${String(val).replace(/"/g, '""')}"`;
    });
    csvRows.push(values.join(","));
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

export const SurveyorsTab: React.FC<SurveyorsTabProps> = ({ records }) => {
  const [subtab, setSubtab] = useState<"overview" | "individual" | "short">("overview");

  // Filter out records without surveyor
  const surveyorRecords = useMemo(() => records.filter((r) => Boolean(r.surveyor)), [records]);

  // Unique surveyor list
  const surveyorList = useMemo(() => {
    return Array.from(new Set(surveyorRecords.map((r) => r.surveyor))).sort();
  }, [surveyorRecords]);

  // ── SUBTAB 1: Overview & Performance Summary ──
  const summaryData = useMemo(() => {
    const map: Record<string, any> = {};

    surveyorRecords.forEach((r) => {
      const name = r.surveyor;
      if (!map[name]) {
        map[name] = {
          surveyor: name,
          total: 0,
          passenger: 0,
          goods: 0,
          directions: new Set<string>(),
          vehicleTypes: new Set<string>(),
          firstEntry: "99:99:99",
          lastEntry: "00:00:00",
          totalDurationSec: 0,
          durationCount: 0,
          suspiciousOD: 0,
        };
      }
      map[name].total++;
      const st = (r.survey_type || "").toLowerCase();
      if (st === "passenger") map[name].passenger++;
      if (st === "goods") map[name].goods++;
      if (r.direction) map[name].directions.add(r.direction);
      if (r.vehicle_type) map[name].vehicleTypes.add(r.vehicle_type);
      if (r.sample_quality_suspicious) map[name].suspiciousOD++;

      if (r.start_time && r.start_time < map[name].firstEntry) {
        map[name].firstEntry = r.start_time;
      }
      if (r.end_time && r.end_time > map[name].lastEntry) {
        map[name].lastEntry = r.end_time;
      }
      if (r.entry_duration_sec && r.entry_duration_sec > 0) {
        map[name].totalDurationSec += r.entry_duration_sec;
        map[name].durationCount++;
      }
    });

    return Object.values(map)
      .map((item) => ({
        surveyor: item.surveyor,
        totalSurveys: item.total,
        passengerSurveys: item.passenger,
        goodsSurveys: item.goods,
        directions: Array.from(item.directions).sort().join(", "),
        vehicleTypes: Array.from(item.vehicleTypes).sort().join(", "),
        firstEntry: item.firstEntry === "99:99:99" ? "-" : item.firstEntry,
        lastEntry: item.lastEntry === "00:00:00" ? "-" : item.lastEntry,
        avgDurationMins:
          item.durationCount > 0 ? (item.totalDurationSec / item.durationCount / 60).toFixed(2) : "0.00",
        suspiciousOD: item.suspiciousOD,
      }))
      .sort((a, b) => b.totalSurveys - a.totalSurveys);
  }, [surveyorRecords]);

  // Chart data for surveys per surveyor
  const chartData = useMemo(() => {
    return [...summaryData].reverse().slice(0, 15);
  }, [summaryData]);

  // ── SUBTAB 2: Individual Surveyor State ──
  const [selectedSurveyor, setSelectedSurveyor] = useState<string>("");

  React.useEffect(() => {
    if (surveyorList.length > 0 && !selectedSurveyor) {
      setSelectedSurveyor(surveyorList[0]);
    }
  }, [surveyorList, selectedSurveyor]);

  const individualStats = useMemo(() => {
    if (!selectedSurveyor) return null;
    const sRecords = surveyorRecords.filter((r) => r.surveyor === selectedSurveyor);
    const total = sRecords.length;
    const pass = sRecords.filter((r) => (r.survey_type || "").toLowerCase() === "passenger").length;
    const goods = sRecords.filter((r) => (r.survey_type || "").toLowerCase() === "goods").length;
    const susp = sRecords.filter((r) => r.sample_quality_suspicious).length;

    let totalDur = 0;
    let durCount = 0;
    let minDur = 999999;
    const hourlyMap: Record<number, number> = {};
    const vtypeMap: Record<string, number> = {};

    sRecords.forEach((r) => {
      if (r.entry_duration_sec && r.entry_duration_sec > 0) {
        totalDur += r.entry_duration_sec;
        durCount++;
        if (r.entry_duration_sec < minDur) minDur = r.entry_duration_sec;
      }
      if (r.start_time) {
        const h = parseInt(r.start_time.split(":")[0], 10);
        if (!isNaN(h)) hourlyMap[h] = (hourlyMap[h] || 0) + 1;
      }
      if (r.vehicle_type) {
        vtypeMap[r.vehicle_type] = (vtypeMap[r.vehicle_type] || 0) + 1;
      }
    });

    const avgDur = durCount > 0 ? (totalDur / durCount / 60).toFixed(2) : "0.00";
    const fastest = minDur !== 999999 ? formatSeconds(minDur) : "-";

    const hourlyData = [];
    for (let h = 0; h < 24; h++) {
      if (hourlyMap[h] !== undefined || (h >= 6 && h <= 22)) {
        hourlyData.push({ hour: `${String(h).padStart(2, "0")}:00`, count: hourlyMap[h] || 0 });
      }
    }

    const vtypeData = Object.keys(vtypeMap).map((k) => ({ name: k, value: vtypeMap[k] }));

    return {
      total,
      pass,
      goods,
      susp,
      avgDur,
      fastest,
      hourlyData,
      vtypeData,
      records: sRecords,
    };
  }, [selectedSurveyor, surveyorRecords]);

  // ── SUBTAB 3: Short Entry Duration Thresholds ──
  const [threshMin, setThreshMin] = useState<number>(4);
  const [threshSec, setThreshSec] = useState<number>(0);

  const totalThreshSec = threshMin * 60 + threshSec;

  const shortEntryData = useMemo(() => {
    const flagged = records.filter(
      (r) => r.entry_duration_sec !== undefined && r.entry_duration_sec >= 0 && r.entry_duration_sec < totalThreshSec
    );

    const sMap: Record<string, { count: number; shortest: number; totalSec: number }> = {};
    flagged.forEach((r) => {
      const name = r.surveyor || "Unknown";
      if (!sMap[name]) sMap[name] = { count: 0, shortest: 999999, totalSec: 0 };
      sMap[name].count++;
      const dur = r.entry_duration_sec || 0;
      sMap[name].totalSec += dur;
      if (dur < sMap[name].shortest) sMap[name].shortest = dur;
    });

    const summary = Object.keys(sMap)
      .map((name) => ({
        surveyor: name,
        shortEntries: sMap[name].count,
        shortestDuration: formatSeconds(sMap[name].shortest === 999999 ? 0 : sMap[name].shortest),
        avgDuration: formatSeconds(sMap[name].totalSec / sMap[name].count),
      }))
      .sort((a, b) => b.shortEntries - a.shortEntries);

    let shortestEntrySec = 0;
    if (flagged.length > 0) {
      shortestEntrySec = Math.min(...flagged.map((r) => r.entry_duration_sec || 0));
    }

    return {
      flagged,
      summary,
      totalShort: flagged.length,
      surveyorsCount: Object.keys(sMap).length,
      shortestEntry: formatSeconds(shortestEntrySec),
      mostFlagged: summary[0]?.surveyor || "-",
    };
  }, [records, totalThreshSec]);

  return (
    <div className="space-y-4 overflow-y-auto p-4">
      {/* Tab Header & Subtab Switcher */}
      <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-center">
        <div>
          <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
            👷 Surveyor Performance & Activity Monitoring
          </h2>
          <p className="text-xs text-slate-500">Track enumerator speeds, shifts, suspicious logs, and volumes</p>
        </div>

        {/* Subtab Pills */}
        <div className="flex rounded-lg bg-slate-200/80 p-1 dark:bg-slate-800">
          <button
            onClick={() => setSubtab("overview")}
            className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
              subtab === "overview"
                ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-900 dark:text-indigo-300"
                : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
            }`}
          >
            📊 Overview & Performance
          </button>
          <button
            onClick={() => setSubtab("individual")}
            className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
              subtab === "individual"
                ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-900 dark:text-indigo-300"
                : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
            }`}
          >
            👤 Individual Activity
          </button>
          <button
            onClick={() => setSubtab("short")}
            className={`rounded-md px-3 py-1 text-xs font-semibold transition ${
              subtab === "short"
                ? "bg-white text-indigo-700 shadow-sm dark:bg-slate-900 dark:text-indigo-300"
                : "text-slate-600 hover:text-slate-900 dark:text-slate-400"
            }`}
          >
            ⏱️ Short Entry Duration
          </button>
        </div>
      </div>

      {/* ── SUBTAB 1: OVERVIEW ── */}
      {subtab === "overview" && (
        <div className="space-y-4">
          <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">
              Surveys per Surveyor (Top Enumerators)
            </h3>
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  layout="vertical"
                  margin={{ top: 5, right: 20, left: 60, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.3} />
                  <XAxis type="number" tick={{ fontSize: 11 }} />
                  <YAxis type="category" dataKey="surveyor" tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                  />
                  <Bar dataKey="totalSurveys" fill="#4f46e5" radius={[0, 4, 4, 0]} name="Total Surveys" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
                Surveyor Summary Table ({summaryData.length} Surveyors)
              </h3>
              <button
                onClick={() => exportCsv(summaryData, "surveyor_performance_summary.csv")}
                className="flex items-center gap-1.5 rounded bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
              >
                <Download className="h-3 w-3" />
                <span>Export CSV</span>
              </button>
            </div>
            <div className="max-h-96 overflow-auto">
              <table className="w-full text-left text-xs">
                <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                  <tr>
                    <th className="p-2.5">Surveyor</th>
                    <th className="p-2.5">Total Surveys</th>
                    <th className="p-2.5">Passenger</th>
                    <th className="p-2.5">Goods</th>
                    <th className="p-2.5">Directions</th>
                    <th className="p-2.5">Vehicle Types</th>
                    <th className="p-2.5">First Entry</th>
                    <th className="p-2.5">Last Entry</th>
                    <th className="p-2.5">Avg Duration</th>
                    <th className="p-2.5">Suspicious OD</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {summaryData.map((row) => (
                    <tr key={row.surveyor} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                      <td className="p-2.5 font-bold text-slate-900 dark:text-slate-100">{row.surveyor}</td>
                      <td className="p-2.5 font-mono font-bold text-indigo-600">{row.totalSurveys}</td>
                      <td className="p-2.5 text-blue-600">{row.passengerSurveys}</td>
                      <td className="p-2.5 text-purple-600">{row.goodsSurveys}</td>
                      <td className="p-2.5 max-w-[150px] truncate" title={row.directions}>{row.directions}</td>
                      <td className="p-2.5 max-w-[200px] truncate" title={row.vehicleTypes}>{row.vehicleTypes}</td>
                      <td className="p-2.5 font-mono">{row.firstEntry}</td>
                      <td className="p-2.5 font-mono">{row.lastEntry}</td>
                      <td className="p-2.5 font-mono">{row.avgDurationMins}m</td>
                      <td className="p-2.5 font-mono font-bold text-rose-600">{row.suspiciousOD}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* ── SUBTAB 2: INDIVIDUAL ACTIVITY ── */}
      {subtab === "individual" && individualStats && (
        <div className="space-y-4">
          {/* Selectbox */}
          <div className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <label className="text-xs font-bold text-slate-700 dark:text-slate-300">
              Select Surveyor to Inspect:
            </label>
            <select
              value={selectedSurveyor}
              onChange={(e) => setSelectedSurveyor(e.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-xs font-semibold text-slate-800 shadow-sm focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
            >
              {surveyorList.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>

          {/* Metric Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
            <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-slate-500">Total Surveys</div>
              <div className="text-xl font-bold text-slate-900 dark:text-slate-100">{individualStats.total}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-blue-600">Passenger</div>
              <div className="text-xl font-bold text-blue-900 dark:text-blue-100">{individualStats.pass}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-purple-600">Goods</div>
              <div className="text-xl font-bold text-purple-900 dark:text-purple-100">{individualStats.goods}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-slate-500">Avg Entry Time</div>
              <div className="text-xl font-bold text-slate-900 dark:text-slate-100">{individualStats.avgDur} min</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-emerald-600">Fastest Entry</div>
              <div className="text-xl font-bold text-emerald-900 dark:text-emerald-100">{individualStats.fastest}</div>
            </div>
            <div className="rounded-xl border border-rose-200 bg-rose-50/40 p-3 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
              <div className="text-xs text-rose-700 dark:text-rose-300">Suspicious ODs</div>
              <div className="text-xl font-bold text-rose-900 dark:text-rose-100">{individualStats.susp}</div>
            </div>
          </div>

          {/* Charts Row */}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h4 className="mb-2 text-xs font-bold text-slate-700 dark:text-slate-300">
                Hourly Activity ({selectedSurveyor})
              </h4>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={individualStats.hourlyData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                    <XAxis dataKey="hour" tick={{ fontSize: 10 }} />
                    <YAxis tick={{ fontSize: 10 }} />
                    <Tooltip />
                    <Bar dataKey="count" fill="#4f46e5" radius={[3, 3, 0, 0]} name="Surveys" />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <h4 className="mb-2 text-xs font-bold text-slate-700 dark:text-slate-300">
                Vehicle Types Surveyed ({selectedSurveyor})
              </h4>
              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={individualStats.vtypeData}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      outerRadius={70}
                      label={({ name, percent }) => `${name}: ${((percent || 0) * 100).toFixed(0)}%`}
                    >
                      {individualStats.vtypeData.map((_, idx) => (
                        <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ── SUBTAB 3: SHORT ENTRY DURATION ── */}
      {subtab === "short" && (
        <div className="space-y-4">
          {/* Threshold Inputs */}
          <div className="flex flex-wrap items-center gap-4 rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">Threshold Minutes:</label>
              <input
                type="number"
                min={0}
                max={60}
                value={threshMin}
                onChange={(e) => setThreshMin(Number(e.target.value))}
                className="w-16 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">Threshold Seconds:</label>
              <input
                type="number"
                min={0}
                max={59}
                step={5}
                value={threshSec}
                onChange={(e) => setThreshSec(Number(e.target.value))}
                className="w-16 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs dark:border-slate-700 dark:bg-slate-800"
              />
            </div>
            <div className="text-xs text-slate-500">
              Flagging entries under <b>{threshMin}m {threshSec}s</b> ({totalThreshSec} seconds)
            </div>
          </div>

          {/* Metric Cards */}
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
              <div className="text-xs text-rose-700 dark:text-rose-300">Short Entries</div>
              <div className="mt-1 text-2xl font-bold text-rose-900 dark:text-rose-100">{shortEntryData.totalShort}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-slate-500">Surveyors Flagged</div>
              <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{shortEntryData.surveyorsCount}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-slate-500">Shortest Entry</div>
              <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">{shortEntryData.shortestEntry}</div>
            </div>
            <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
              <div className="text-xs text-slate-500">Most Flagged Surveyor</div>
              <div className="mt-1 truncate text-lg font-bold text-slate-900 dark:text-slate-100">{shortEntryData.mostFlagged}</div>
            </div>
          </div>

          {/* Summary Table */}
          <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
            <div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-slate-800">
              <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Summary by Surveyor</h3>
              <button
                onClick={() => exportCsv(shortEntryData.summary, "short_entry_surveyor_summary.csv")}
                className="flex items-center gap-1.5 rounded bg-indigo-50 px-2.5 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
              >
                <Download className="h-3 w-3" />
                <span>Export CSV</span>
              </button>
            </div>
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-100 dark:bg-slate-800">
                <tr>
                  <th className="p-2.5">Surveyor</th>
                  <th className="p-2.5">Short Entries</th>
                  <th className="p-2.5">Shortest Duration</th>
                  <th className="p-2.5">Avg Duration</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {shortEntryData.summary.map((row) => (
                  <tr key={row.surveyor} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="p-2.5 font-bold">{row.surveyor}</td>
                    <td className="p-2.5 font-mono font-bold text-rose-600">{row.shortEntries}</td>
                    <td className="p-2.5 font-mono">{row.shortestDuration}</td>
                    <td className="p-2.5 font-mono">{row.avgDuration}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};

