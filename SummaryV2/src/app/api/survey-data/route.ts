import { NextRequest, NextResponse } from "next/server";
import { querySurveyRecords } from "@/lib/db";
import { GlobalFilterState } from "@/lib/types";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);

    // Parse array query params (supporting comma-separated and multiple key values)
    const parseArrayParam = (paramName: string): string[] | undefined => {
      const all = searchParams.getAll(paramName);
      if (all.length === 0) {
        const single = searchParams.get(paramName);
        if (single === null) return undefined;
        return single.split(",").map((s) => s.trim()).filter(Boolean);
      }
      return all.flatMap((item) => item.split(",")).map((s) => s.trim()).filter(Boolean);
    };

    const filters: GlobalFilterState = {
      dateFrom: searchParams.get("dateFrom") || "",
      dateTo: searchParams.get("dateTo") || "",
      timeFrom: searchParams.get("timeFrom") || "",
      timeTo: searchParams.get("timeTo") || "",
      surveyTypes: parseArrayParam("surveyType") || (searchParams.has("surveyType") ? [] : (undefined as any)),
      directions: parseArrayParam("direction") || (searchParams.has("direction") ? [] : (undefined as any)),
      vehicleTypes: parseArrayParam("vehicleType") || (searchParams.has("vehicleType") ? [] : (undefined as any)),
      surveyors: parseArrayParam("surveyor") || (searchParams.has("surveyor") ? [] : (undefined as any)),
    };

    const page = parseInt(searchParams.get("page") || "1", 10);
    const pageSize = parseInt(searchParams.get("pageSize") || "50", 10);
    const sortBy = searchParams.get("sortBy") || "date";
    const sortOrder = (searchParams.get("sortOrder") || "desc") as "asc" | "desc";

    const result = await querySurveyRecords(filters, { page, pageSize, sortBy, sortOrder });
    return NextResponse.json(result);
  } catch (error) {
    console.error("Error in /api/survey-data:", error);
    return NextResponse.json(
      { error: "Failed to query survey records" },
      { status: 500 }
    );
  }
}

