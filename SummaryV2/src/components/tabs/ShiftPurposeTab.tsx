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
  CartesianGrid,
} from "recharts";

interface ShiftPurposeTabProps {
  records: SurveyRecord[];
}

const SHIFT_COLORS = ["#10b981", "#ef4444", "#6b7280", "#f59e0b"];

export const ShiftPurposeTab: React.FC<ShiftPurposeTabProps> = ({ records }) => {
  const { shiftData, freqData, passengerPurposeData, goodsCommodityData } = useMemo(() => {
    const shiftMap: Record<string, number> = {};
    const freqMap: Record<string, number> = {};
    const passPurposeMap: Record<string, number> = {};
    const goodsCommMap: Record<string, number> = {};

    records.forEach((r) => {
      // 1. Shift
      if (r.likely_shift && r.likely_shift.trim()) {
        const s = r.likely_shift.trim();
        shiftMap[s] = (shiftMap[s] || 0) + 1;
      }

      // 2. Frequency
      if (r.trip_frequency && r.trip_frequency.trim()) {
        const f = r.trip_frequency.trim();
        freqMap[f] = (freqMap[f] || 0) + 1;
      }

      // 3. Purpose / Commodity
      const st = (r.survey_type || "").toLowerCase();
      const p = r.trip_purpose_or_commodity?.trim();
      if (p) {
        if (st === "passenger") {
          passPurposeMap[p] = (passPurposeMap[p] || 0) + 1;
        } else if (st === "goods") {
          goodsCommMap[p] = (goodsCommMap[p] || 0) + 1;
        }
      }
    });

    const shiftData = Object.keys(shiftMap)
      .map((k) => ({ name: k, value: shiftMap[k] }))
      .sort((a, b) => b.value - a.value);

    const freqData = Object.keys(freqMap)
      .map((k) => ({ frequency: k, count: freqMap[k] }))
      .sort((a, b) => b.count - a.count);

    const passengerPurposeData = Object.keys(passPurposeMap)
      .map((k) => ({ purpose: k, count: passPurposeMap[k] }))
      .sort((a, b) => b.count - a.count);

    const goodsCommodityData = Object.keys(goodsCommMap)
      .map((k) => ({ commodity: k, count: goodsCommMap[k] }))
      .sort((a, b) => b.count - a.count);

    return { shiftData, freqData, passengerPurposeData, goodsCommodityData };
  }, [records]);

  return (
    <div className="space-y-6 overflow-y-auto p-4">
      <div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
          🔁 Shift, Frequency, Purpose and Commodity
        </h2>
        <p className="text-xs text-slate-500">Willingness to shift, travel patterns, and load categorization</p>
      </div>

      {/* Row 1: Shift & Frequency */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Likely to Shift */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">
            Likely to Shift to Proposed Corridor?
          </h3>
          <div className="h-64 w-full">
            {shiftData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={shiftData}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={({ name, percent }) => `${name}: ${((percent || 0) * 100).toFixed(0)}%`}
                  >
                    {shiftData.map((_, idx) => (
                      <Cell key={`shift-${idx}`} fill={SHIFT_COLORS[idx % SHIFT_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No shift response data available
              </div>
            )}
          </div>
        </div>

        {/* Trip Frequency */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">Trip Frequency</h3>
          <div className="h-64 w-full">
            {freqData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={freqData} margin={{ top: 10, right: 10, left: -20, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                  <XAxis dataKey="frequency" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#4f46e5" radius={[4, 4, 0, 0]} name="Count" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No frequency data available
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Row 2: Purpose & Commodity */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Passenger Purpose */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">Passenger Purpose</h3>
          <div className="h-64 w-full">
            {passengerPurposeData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={passengerPurposeData} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                  <XAxis dataKey="purpose" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Count" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No passenger purpose data available
              </div>
            )}
          </div>
        </div>

        {/* Goods Commodity */}
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 text-sm font-bold text-slate-800 dark:text-slate-200">Goods Commodity</h3>
          <div className="h-64 w-full">
            {goodsCommodityData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={goodsCommodityData} margin={{ top: 10, right: 10, left: -20, bottom: 25 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.3} />
                  <XAxis dataKey="commodity" tick={{ fontSize: 10 }} angle={-30} textAnchor="end" interval={0} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#8b5cf6" radius={[4, 4, 0, 0]} name="Count" />
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-400">
                No goods commodity data available
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

