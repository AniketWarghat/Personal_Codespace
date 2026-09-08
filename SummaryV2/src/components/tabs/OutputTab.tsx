"use client";

import React, { useMemo, useState } from "react";
import { SurveyRecord } from "@/lib/types";
import { Download, Search, MapPin } from "lucide-react";

interface OutputTabProps {
  records: SurveyRecord[];
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

export const OutputTab: React.FC<OutputTabProps> = ({ records }) => {
  const [searchTerm, setSearchTerm] = useState("");

  const { topPairs, topOrigins, topDestinations } = useMemo(() => {
    const pairMap: Record<string, { origin: string; destination: string; count: number; passenger: number; goods: number }> = {};
    const oMap: Record<string, number> = {};
    const dMap: Record<string, number> = {};

    records.forEach((r) => {
      const o = r.origin?.trim();
      const d = r.destination?.trim();
      const st = (r.survey_type || "").toLowerCase();

      if (o) oMap[o] = (oMap[o] || 0) + 1;
      if (d) dMap[d] = (dMap[d] || 0) + 1;

      if (o && d) {
        const key = `${o} ➔ ${d}`;
        if (!pairMap[key]) {
          pairMap[key] = { origin: o, destination: d, count: 0, passenger: 0, goods: 0 };
        }
        pairMap[key].count++;
        if (st === "passenger") pairMap[key].passenger++;
        else if (st === "goods") pairMap[key].goods++;
      }
    });

    const topPairs = Object.values(pairMap).sort((a, b) => b.count - a.count);
    const topOrigins = Object.keys(oMap).map((k) => ({ location: k, count: oMap[k] })).sort((a, b) => b.count - a.count);
    const topDestinations = Object.keys(dMap).map((k) => ({ location: k, count: dMap[k] })).sort((a, b) => b.count - a.count);

    return { topPairs, topOrigins, topDestinations };
  }, [records]);

  const filteredPairs = useMemo(() => {
    if (!searchTerm) return topPairs;
    const q = searchTerm.toLowerCase();
    return topPairs.filter(
      (p) => p.origin.toLowerCase().includes(q) || p.destination.toLowerCase().includes(q)
    );
  }, [topPairs, searchTerm]);

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
          🗺️ Origin–Destination Spatial Analysis & Corridors
        </h2>
        <p className="text-xs text-slate-500">Major OD trip desires, dominant traffic corridors, and node hubs</p>
      </div>

      {/* Top Origins & Destinations Summary Cards */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Top Origins */}
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-200 p-3.5 dark:border-slate-800">
            <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200">Top 10 Origins (Trip Production)</h3>
            <button
              onClick={() => exportCsv(topOrigins, "top_origins.csv")}
              className="flex items-center gap-1 rounded bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
            >
              <Download className="h-3 w-3" />
              <span>CSV</span>
            </button>
          </div>
          <div className="max-h-60 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                <tr>
                  <th className="p-2">Rank</th>
                  <th className="p-2">Origin Location</th>
                  <th className="p-2">Total Trips</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {topOrigins.slice(0, 10).map((row, idx) => (
                  <tr key={`orig-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="p-2 font-mono text-slate-400">#{idx + 1}</td>
                    <td className="p-2 font-bold text-slate-800 dark:text-slate-200">{row.location}</td>
                    <td className="p-2 font-mono font-bold text-indigo-600">{row.count.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Top Destinations */}
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-200 p-3.5 dark:border-slate-800">
            <h3 className="text-xs font-bold text-slate-800 dark:text-slate-200">Top 10 Destinations (Trip Attraction)</h3>
            <button
              onClick={() => exportCsv(topDestinations, "top_destinations.csv")}
              className="flex items-center gap-1 rounded bg-indigo-50 px-2 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
            >
              <Download className="h-3 w-3" />
              <span>CSV</span>
            </button>
          </div>
          <div className="max-h-60 overflow-auto">
            <table className="w-full text-left text-xs">
              <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
                <tr>
                  <th className="p-2">Rank</th>
                  <th className="p-2">Destination Location</th>
                  <th className="p-2">Total Trips</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {topDestinations.slice(0, 10).map((row, idx) => (
                  <tr key={`dest-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                    <td className="p-2 font-mono text-slate-400">#{idx + 1}</td>
                    <td className="p-2 font-bold text-slate-800 dark:text-slate-200">{row.location}</td>
                    <td className="p-2 font-mono font-bold text-purple-600">{row.count.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Top OD Pairs Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="flex flex-col justify-between gap-3 border-b border-slate-200 p-3.5 sm:flex-row sm:items-center dark:border-slate-800">
          <div className="flex items-center gap-2">
            <MapPin className="h-4 w-4 text-indigo-600" />
            <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">
              Dominant OD Desire Pairs ({filteredPairs.length} Corridors)
            </h3>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-400" />
              <input
                type="text"
                placeholder="Search origin / destination..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="rounded-lg border border-slate-300 bg-white py-1 pl-8 pr-3 text-xs shadow-sm focus:border-indigo-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
              />
            </div>
            <button
              onClick={() => exportCsv(filteredPairs, "dominant_od_pairs.csv")}
              className="flex items-center gap-1.5 rounded bg-indigo-50 px-3 py-1 text-xs font-semibold text-indigo-700 hover:bg-indigo-100 dark:bg-indigo-950/70 dark:text-indigo-300"
            >
              <Download className="h-3.5 w-3.5" />
              <span>Export CSV</span>
            </button>
          </div>
        </div>

        <div className="max-h-96 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
              <tr>
                <th className="p-2.5">Rank</th>
                <th className="p-2.5">Origin</th>
                <th className="p-2.5">Destination</th>
                <th className="p-2.5">Total Trips</th>
                <th className="p-2.5">Passenger Trips</th>
                <th className="p-2.5">Goods Trips</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {filteredPairs.slice(0, 100).map((pair, idx) => (
                <tr key={`pair-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="p-2.5 font-mono text-slate-400">#{idx + 1}</td>
                  <td className="p-2.5 font-bold text-slate-900 dark:text-slate-100">{pair.origin}</td>
                  <td className="p-2.5 font-bold text-slate-900 dark:text-slate-100">{pair.destination}</td>
                  <td className="p-2.5 font-mono font-bold text-indigo-600">{pair.count.toLocaleString()}</td>
                  <td className="p-2.5 font-mono text-blue-600">{pair.passenger}</td>
                  <td className="p-2.5 font-mono text-purple-600">{pair.goods}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

