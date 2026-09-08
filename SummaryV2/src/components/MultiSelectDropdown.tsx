"use client";

import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, Check, X } from "lucide-react";

interface MultiSelectDropdownProps {
  label: string;
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
}

export const MultiSelectDropdown: React.FC<MultiSelectDropdownProps> = ({
  label,
  options,
  selected,
  onChange,
  placeholder = "Select options...",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const filteredOptions = options.filter((opt) =>
    opt.toLowerCase().includes(search.toLowerCase())
  );

  const isAllSelected = options.length > 0 && selected.length === options.length;
  const isSomeSelected = selected.length > 0 && selected.length < options.length;

  const handleToggleOption = (opt: string) => {
    if (selected.includes(opt)) {
      onChange(selected.filter((item) => item !== opt));
    } else {
      onChange([...selected, opt]);
    }
  };

  const handleToggleAll = () => {
    if (isAllSelected) {
      onChange([]);
    } else {
      onChange([...options]);
    }
  };

  return (
    <div className="flex flex-col gap-1 text-sm" ref={dropdownRef}>
      <div className="flex items-center justify-between">
        <label className="font-medium text-slate-700 dark:text-slate-300">{label}</label>
        <span className="text-xs text-slate-500">
          {selected.length} / {options.length}
        </span>
      </div>

      <div className="relative">
        <button
          type="button"
          onClick={() => setIsOpen(!isOpen)}
          className="flex w-full items-center justify-between rounded-lg border border-slate-300 bg-white px-3 py-2 text-left text-sm shadow-sm transition hover:border-indigo-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        >
          <span className="truncate">
            {selected.length === 0
              ? "None selected (0)"
              : isAllSelected
              ? "All Selected"
              : `${selected.length} selected`}
          </span>
          <ChevronDown
            className={`h-4 w-4 text-slate-400 transition-transform ${
              isOpen ? "rotate-180" : ""
            }`}
          />
        </button>

        {isOpen && (
          <div className="absolute z-50 mt-1 max-h-60 w-full overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900">
            {/* Search Input */}
            <div className="border-b border-slate-100 p-2 dark:border-slate-800">
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search..."
                className="w-full rounded border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs text-slate-800 focus:border-indigo-500 focus:bg-white focus:outline-none dark:border-slate-700 dark:bg-slate-800 dark:text-slate-200"
              />
            </div>

            {/* Select All Toggle */}
            <div
              onClick={handleToggleAll}
              className="flex cursor-pointer items-center justify-between border-b border-slate-100 px-3 py-2 text-xs font-semibold text-indigo-600 hover:bg-indigo-50 dark:border-slate-800 dark:text-indigo-400 dark:hover:bg-indigo-950/40"
            >
              <span>{isAllSelected ? "Deselect All" : "Select All"}</span>
              <div
                className={`flex h-4 w-4 items-center justify-center rounded border ${
                  isAllSelected
                    ? "border-indigo-600 bg-indigo-600 text-white"
                    : isSomeSelected
                    ? "border-indigo-600 bg-indigo-100 text-indigo-600"
                    : "border-slate-300 dark:border-slate-600"
                }`}
              >
                {isAllSelected && <Check className="h-3 w-3" />}
                {isSomeSelected && <div className="h-1.5 w-1.5 rounded-full bg-indigo-600" />}
              </div>
            </div>

            {/* Options List */}
            <div className="max-h-40 overflow-y-auto p-1">
              {filteredOptions.length === 0 ? (
                <div className="p-2 text-center text-xs text-slate-400">No matching options</div>
              ) : (
                filteredOptions.map((opt) => {
                  const isSelected = selected.includes(opt);
                  return (
                    <div
                      key={opt}
                      onClick={() => handleToggleOption(opt)}
                      className={`flex cursor-pointer items-center justify-between rounded px-2.5 py-1.5 text-xs transition ${
                        isSelected
                          ? "bg-indigo-50/70 font-medium text-indigo-900 dark:bg-indigo-950/30 dark:text-indigo-200"
                          : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                      }`}
                    >
                      <span className="truncate pr-2">{opt}</span>
                      <div
                        className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                          isSelected
                            ? "border-indigo-600 bg-indigo-600 text-white"
                            : "border-slate-300 dark:border-slate-600"
                        }`}
                      >
                        {isSelected && <Check className="h-3 w-3" />}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

