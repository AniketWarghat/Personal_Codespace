"use client";

import React, { useMemo } from "react";
import { SurveyRecord } from "@/lib/types";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";

interface SummaryTabProps {
  records: SurveyRecord[];
  totalFiltered: number;
}

export const SummaryTab: React.FC<SummaryTabProps> = ({ records, totalFiltered }) => {
  const stats = useMemo(() => {
    const total = totalFiltered;
    let passengerCount = 0;
    let goodsCount = 0;
    const surveyorsSet = new Set<string>();
    const vehicleCounts: Record<string, number> = {};
    let odValidCount = 0;
    let suspiciousCount = 0;
    let totalDurationSec = 0;
    let validDurationCount = 0;

    const hourlyMap: Record<number, number> = {};
    const dailyMap: Record<string, number> = {};

    records.forEach((r) => {
      const st = (r.survey_type || "").toLowerCase();
      if (st === "passenger") passengerCount++;
      else if (st === "goods") goodsCount++;

      if (r.surveyor) surveyorsSet.add(r.surveyor);
      if (r.vehicle_type) {
        vehicleCounts[r.vehicle_type] = (vehicleCounts[r.vehicle_type] || 0) + 1;
      }
      if (r.has_origin_destination) odValidCount++;
      if (r.sample_quality_suspicious) suspiciousCount++;

      if (r.entry_duration_sec && r.entry_duration_sec > 0) {
        totalDurationSec += r.entry_duration_sec;
        validDurationCount++;
      }

      // Hourly aggregation
      if (r.start_time) {
        const hour = parseInt(r.start_time.split(":")[0], 10);
        if (!isNaN(hour)) {
          hourlyMap[hour] = (hourlyMap[hour] || 0) + 1;
        }
      }

      // Daily aggregation
      if (r.date) {
        dailyMap[r.date] = (dailyMap[r.date] || 0) + 1;
      }
    });

    let topVehicle = "N/A";
    let maxVCount = 0;
    for (const [v, c] of Object.entries(vehicleCounts)) {
      if (c > maxVCount) {
        maxVCount = c;
        topVehicle = v;
      }
    }

    const odCompleteness = total > 0 ? ((odValidCount / total) * 100).toFixed(1) : "0.0";
    const suspiciousPct = total > 0 ? ((suspiciousCount / total) * 100).toFixed(1) : "0.0";
    const avgDurationMins =
      validDurationCount > 0 ? (totalDurationSec / validDurationCount / 60).toFixed(2) : "0.00";

    // Hourly chart data (hours 0 to 23)
    const hourlyData = [];
    for (let h = 0; h < 24; h++) {
      if (hourlyMap[h] !== undefined || (h >= 6 && h <= 22)) {
        hourlyData.push({
          hour: `${String(h).padStart(2, "0")}:00`,
          count: hourlyMap[h] || 0,
        });
      }
    }

    // Daily chart data
    const dailyData = Object.keys(dailyMap)
      .sort()
      .map((date) => ({
        date,
        count: dailyMap[date],
      }));

    return {
      total,
      passengerCount,
      goodsCount,
      activeSurveyors: surveyorsSet.size,
      topVehicle,
      odCompleteness,
      suspiciousCount,
      suspiciousPct,
      avgDurationMins,
      hourlyData,
      dailyData,
    };
  }, [records, totalFiltered]);

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      {/* Tab Header */}
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">📊 Survey Summary</h2>
        <p className="text-xs text-slate-500">Real-time macro statistics and temporal survey distribution</p>
      </div>

      {/* Row 1 Metric Cards (6 cards) */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-slate-500">Total Surveys</div>
          <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {stats.total.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-blue-600">Passenger</div>
          <div className="mt-1 text-2xl font-bold text-blue-900 dark:text-blue-100">
            {stats.passengerCount.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-purple-600">Goods</div>
          <div className="mt-1 text-2xl font-bold text-purple-900 dark:text-purple-100">
            {stats.goodsCount.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-slate-500">Active Surveyors</div>
          <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {stats.activeSurveyors}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-slate-500">Top Vehicle</div>
          <div className="mt-1 truncate text-lg font-bold text-slate-900 dark:text-slate-100" title={stats.topVehicle}>
            {stats.topVehicle}
          </div>
        </div>

        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-emerald-600">OD Completeness</div>
          <div className="mt-1 text-2xl font-bold text-emerald-900 dark:text-emerald-100">
            {stats.odCompleteness}%
          </div>
        </div>
      </div>

      {/* Row 2 Metric Cards (3 cards) */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-3.5 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <div className="text-xs font-medium text-slate-500">Avg Entry Duration</div>
          <div className="mt-1 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {stats.avgDurationMins} min
          </div>
        </div>

        <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
          <div className="text-xs font-medium text-rose-700 dark:text-rose-300">Suspicious OD Records</div>
          <div className="mt-1 text-2xl font-bold text-rose-900 dark:text-rose-100">
            {stats.suspiciousCount.toLocaleString()}
          </div>
        </div>

        <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-3.5 shadow-sm dark:border-rose-900/40 dark:bg-rose-950/20">
          <div className="text-xs font-medium text-rose-700 dark:text-rose-300">Suspicious OD %</div>
          <div className="mt-1 text-2xl font-bold text-rose-900 dark:text-rose-100">
            {stats.suspiciousPct}%
          </div>
        </div>
      </div>

      <hr className="border-slate-200 dark:border-slate-800" />

      {/* Charts Row */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Hourly Distribution */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">
            Hourly Survey Distribution
          </h3>
          <div className="h-64 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.hourlyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                <XAxis dataKey="hour" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "rgba(15, 23, 42, 0.9)",
                    borderRadius: "8px",
                    color: "#fff",
                    fontSize: "12px",
                  }}
                />
                <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} name="Surveys" />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Daily Trend */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">
            Daily Survey Trend
          </h3>
          <div className="h-64 w-full">
            {stats.dailyData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={stats.dailyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                  <XAxis dataKey="date" tick={{ fontSize: 11 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "rgba(15, 23, 42, 0.9)",
                      borderRadius: "8px",
                      color: "#fff",
                      fontSize: "12px",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="count"
                    stroke="#4f46e5"
                    strokeWidth={2.5}
                    dot={{ r: 4, fill: "#4f46e5" }}
                    name="Surveys"
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No daily trend data available
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

