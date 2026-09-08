"use client";

import React, { useMemo } from "react";
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
  SortingState,
} from "@tanstack/react-table";
import { SurveyRecord } from "@/lib/types";
import {
  ArrowUpDown,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  AlertTriangle,
} from "lucide-react";

interface RawDataTableProps {
  records: SurveyRecord[];
  totalCount: number;
  filteredCount: number;
  page: number;
  pageSize: number;
  sortBy: string;
  sortOrder: "asc" | "desc";
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  onSortChange: (sortBy: string, sortOrder: "asc" | "desc") => void;
  isLoading: boolean;
}

const columnHelper = createColumnHelper<SurveyRecord>();

export const RawDataTable: React.FC<RawDataTableProps> = ({
  records,
  filteredCount,
  page,
  pageSize,
  sortBy,
  sortOrder,
  onPageChange,
  onPageSizeChange,
  onSortChange,
  isLoading,
}) => {
  // TanStack columns matching prepare_display() in app-2.py
  const columns = useMemo(
    () => [
      columnHelper.accessor("date", {
        header: "Date",
        cell: (info) => <span className="font-medium text-slate-800 dark:text-slate-200">{info.getValue()}</span>,
      }),
      columnHelper.accessor("start_time", {
        header: "Start Time",
        cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
      }),
      columnHelper.accessor("end_time", {
        header: "End Time",
        cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
      }),
      columnHelper.accessor("entry_duration_sec", {
        header: "Entry Duration (sec)",
        cell: (info) => {
          const val = info.getValue() ?? 0;
          const isShort = val > 0 && val < 60;
          return (
            <span
              className={`rounded px-2 py-0.5 font-mono text-xs font-semibold ${
                isShort
                  ? "bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200"
                  : "text-slate-700 dark:text-slate-300"
              }`}
            >
              {val}s
            </span>
          );
        },
      }),
      columnHelper.accessor("surveyor", {
        header: "Surveyor",
        cell: (info) => <span className="font-semibold text-indigo-950 dark:text-indigo-200">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("contact", {
        header: "Contact",
        cell: (info) => <span className="text-slate-600 dark:text-slate-400">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("survey_type", {
        header: "Survey Type",
        cell: (info) => {
          const val = info.getValue();
          return (
            <span
              className={`inline-flex rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                val?.toLowerCase() === "passenger"
                  ? "bg-blue-100 text-blue-800 dark:bg-blue-950/60 dark:text-blue-300"
                  : "bg-purple-100 text-purple-800 dark:bg-purple-950/60 dark:text-purple-300"
              }`}
            >
              {val || "-"}
            </span>
          );
        },
      }),
      columnHelper.accessor("direction", {
        header: "Direction",
        cell: (info) => <span className="text-slate-700 dark:text-slate-300">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("vehicle_type", {
        header: "Vehicle Type",
        cell: (info) => <span className="font-medium text-slate-800 dark:text-slate-200">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("occupancy", {
        header: "Occupancy",
        cell: (info) => <span className="font-mono text-xs">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("origin", {
        header: "Origin",
        cell: (info) => <span className="text-slate-800 dark:text-slate-200">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("destination", {
        header: "Destination",
        cell: (info) => <span className="text-slate-800 dark:text-slate-200">{info.getValue() || "-"}</span>,
      }),
      columnHelper.accessor("survey_duration_mins", {
        header: "Duration (mins)",
        cell: (info) => <span className="font-mono text-xs">{info.getValue() ?? "-"}</span>,
      }),
      columnHelper.accessor("sample_quality_flags", {
        header: "Sample Quality Flags",
        cell: (info) => {
          const flag = info.getValue();
          if (!flag) return <span className="text-slate-400">-</span>;
          return (
            <span className="inline-flex items-center gap-1 rounded bg-rose-100 px-2 py-0.5 text-xs font-medium text-rose-800 dark:bg-rose-950/60 dark:text-rose-200">
              <AlertTriangle className="h-3 w-3" />
              <span>{flag}</span>
            </span>
          );
        },
      }),
    ],
    []
  );

  const table = useReactTable({
    data: records,
    columns,
    getCoreRowModel: getCoreRowModel(),
    manualSorting: true,
    manualPagination: true,
  });

  const totalPages = Math.ceil(filteredCount / pageSize) || 1;

  const handleHeaderClick = (colId: string) => {
    if (sortBy === colId) {
      onSortChange(colId, sortOrder === "asc" ? "desc" : "asc");
    } else {
      onSortChange(colId, "asc");
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900">
      {/* Table Scrollable Container */}
      <div className="relative flex-1 overflow-auto">
        <table className="w-full border-collapse text-left text-xs">
          <thead className="sticky top-0 z-10 border-b border-slate-200 bg-slate-100/90 backdrop-blur dark:border-slate-800 dark:bg-slate-800/90">
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id}>
                {headerGroup.headers.map((header) => {
                  const colId = header.column.id;
                  const isSorted = sortBy === colId;
                  return (
                    <th
                      key={header.id}
                      onClick={() => handleHeaderClick(colId)}
                      className="cursor-pointer select-none whitespace-nowrap px-3.5 py-3 text-xs font-semibold text-slate-700 transition hover:bg-slate-200/60 dark:text-slate-200 dark:hover:bg-slate-700/60"
                    >
                      <div className="flex items-center gap-1.5">
                        {flexRender(header.column.columnDef.header, header.getContext())}
                        <span className="text-slate-400">
                          {isSorted ? (
                            sortOrder === "asc" ? (
                              <ArrowUp className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
                            ) : (
                              <ArrowDown className="h-3.5 w-3.5 text-indigo-600 dark:text-indigo-400" />
                            )
                          ) : (
                            <ArrowUpDown className="h-3 w-3 opacity-40 hover:opacity-100" />
                          )}
                        </span>
                      </div>
                    </th>
                  );
                })}
              </tr>
            ))}
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {records.length === 0 ? (
              <tr>
                <td colSpan={columns.length} className="p-8 text-center text-slate-500">
                  No survey records match the current filter selection.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr
                  key={row.id}
                  className="transition hover:bg-slate-50/80 dark:hover:bg-slate-800/40"
                >
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="whitespace-nowrap px-3.5 py-2.5">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Footer */}
      <div className="flex items-center justify-between border-t border-slate-200 bg-slate-50/80 px-4 py-2.5 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-950/80 dark:text-slate-400">
        <div className="flex items-center gap-2">
          <span>Showing</span>
          <select
            value={pageSize}
            onChange={(e) => onPageSizeChange(Number(e.target.value))}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-slate-800 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={250}>250</option>
          </select>
          <span>
            records per page ({records.length > 0 ? (page - 1) * pageSize + 1 : 0} -{" "}
            {Math.min(page * pageSize, filteredCount)} of {filteredCount.toLocaleString()})
          </span>
        </div>

        <div className="flex items-center gap-1.5">
          <button
            onClick={() => onPageChange(1)}
            disabled={page <= 1}
            className="rounded p-1 text-slate-500 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-800"
            title="First Page"
          >
            <ChevronsLeft className="h-4 w-4" />
          </button>
          <button
            onClick={() => onPageChange(page - 1)}
            disabled={page <= 1}
            className="rounded p-1 text-slate-500 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-800"
            title="Previous Page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
          <span className="px-2 font-medium text-slate-700 dark:text-slate-300">
            Page {page} of {totalPages}
          </span>
          <button
            onClick={() => onPageChange(page + 1)}
            disabled={page >= totalPages}
            className="rounded p-1 text-slate-500 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-800"
            title="Next Page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>
          <button
            onClick={() => onPageChange(totalPages)}
            disabled={page >= totalPages}
            className="rounded p-1 text-slate-500 hover:bg-slate-200 disabled:opacity-30 dark:hover:bg-slate-800"
            title="Last Page"
          >
            <ChevronsRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

