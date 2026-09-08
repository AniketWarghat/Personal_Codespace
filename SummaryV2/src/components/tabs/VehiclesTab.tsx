"use client";

import React, { useMemo } from "react";
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
  Legend,
  CartesianGrid,
} from "recharts";

interface VehiclesTabProps {
  records: SurveyRecord[];
}

const COLORS = [
  "#1e40af", "#2563eb", "#3b82f6", "#60a5fa", "#93c5fd",
  "#7c3aed", "#8b5cf6", "#a78bfa", "#c4b5fd", "#0d9488", "#14b8a6", "#2dd4bf"
];

export const VehiclesTab: React.FC<VehiclesTabProps> = ({ records }) => {
  const { summaryTable, pieData, stackedBarData } = useMemo(() => {
    const validRecords = records.filter((r) => Boolean(r.vehicle_type));
    const totalV = validRecords.length;

    // Aggregations by survey_type & vehicle_type
    const map: Record<string, { surveyType: string; vehicleType: string; count: number; totalOccupancy: number; occupancyCount: number }> = {};
    const typeCountMap: Record<string, number> = {};
    const stackedMap: Record<string, { vehicleType: string; passenger: number; goods: number }> = {};

    validRecords.forEach((r) => {
      const vt = r.vehicle_type;
      const st = r.survey_type || "Other";
      const key = `${st}___${vt}`;

      if (!map[key]) {
        map[key] = { surveyType: st, vehicleType: vt, count: 0, totalOccupancy: 0, occupancyCount: 0 };
      }
      map[key].count++;
      typeCountMap[vt] = (typeCountMap[vt] || 0) + 1;

      if (!stackedMap[vt]) {
        stackedMap[vt] = { vehicleType: vt, passenger: 0, goods: 0 };
      }
      if (st.toLowerCase() === "passenger") stackedMap[vt].passenger++;
      else if (st.toLowerCase() === "goods") stackedMap[vt].goods++;

      const occ = typeof r.occupancy === "number" ? r.occupancy : parseFloat(String(r.occupancy || ""));
      if (!isNaN(occ) && occ > 0) {
        map[key].totalOccupancy += occ;
        map[key].occupancyCount++;
      }
    });

    const summaryTable = Object.values(map)
      .map((item) => ({
        surveyType: item.surveyType,
        vehicleType: item.vehicleType,
        count: item.count,
        sharePct: totalV > 0 ? ((item.count / totalV) * 100).toFixed(1) : "0.0",
        avgOccupancy: item.occupancyCount > 0 ? (item.totalOccupancy / item.occupancyCount).toFixed(1) : "-",
      }))
      .sort((a, b) => b.count - a.count);

    const pieData = Object.keys(typeCountMap)
      .map((k) => ({ name: k, value: typeCountMap[k] }))
      .sort((a, b) => b.value - a.value);

    const stackedBarData = Object.values(stackedMap).sort((a, b) => (b.passenger + b.goods) - (a.passenger + a.goods));

    return { summaryTable, pieData, stackedBarData };
  }, [records]);

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">🚗 Vehicle Type Analysis</h2>
        <p className="text-xs text-slate-500">Breakdown of vehicle classifications, passenger vs goods share, and occupancy</p>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Pie Chart */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">Vehicle Type Share</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={pieData}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  label={({ name, percent }) => `${name}: ${((percent || 0) * 100).toFixed(0)}%`}
                >
                  {pieData.map((_, idx) => (
                    <Cell key={`cell-${idx}`} fill={COLORS[idx % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Stacked Bar Chart */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">Vehicle Count by Survey Type</h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stackedBarData} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                <XAxis dataKey="vehicleType" angle={-30} textAnchor="end" tick={{ fontSize: 10 }} interval={0} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend verticalAlign="top" height={36} />
                <Bar dataKey="passenger" fill="#3b82f6" name="Passenger" stackId="a" />
                <Bar dataKey="goods" fill="#8b5cf6" name="Goods" stackId="a" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Summary Table */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
        <div className="border-b border-slate-200 p-3.5 dark:border-slate-800">
          <h3 className="text-sm font-bold text-slate-800 dark:text-slate-200">Vehicle Type Summary Breakdown</h3>
        </div>
        <div className="max-h-96 overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-slate-100 dark:bg-slate-800">
              <tr>
                <th className="p-2.5">Survey Type</th>
                <th className="p-2.5">Vehicle Type</th>
                <th className="p-2.5">Count</th>
                <th className="p-2.5">Share (%)</th>
                <th className="p-2.5">Avg Occupancy</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {summaryTable.map((row, idx) => (
                <tr key={`${row.surveyType}-${row.vehicleType}-${idx}`} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                  <td className="p-2.5">
                    <span
                      className={`inline-flex rounded px-2 py-0.5 text-[10px] font-semibold ${
                        row.surveyType.toLowerCase() === "passenger"
                          ? "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300"
                          : "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300"
                      }`}
                    >
                      {row.surveyType}
                    </span>
                  </td>
                  <td className="p-2.5 font-bold text-slate-800 dark:text-slate-200">{row.vehicleType}</td>
                  <td className="p-2.5 font-mono font-bold text-indigo-600">{row.count.toLocaleString()}</td>
                  <td className="p-2.5 font-mono">{row.sharePct}%</td>
                  <td className="p-2.5 font-mono">{row.avgOccupancy}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
