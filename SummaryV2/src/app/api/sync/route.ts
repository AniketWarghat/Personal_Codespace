import { NextResponse } from "next/server";
import { exec } from "child_process";
import path from "path";

export const dynamic = "force-dynamic";

export async function POST() {
  try {
    const pythonScript = path.resolve(process.cwd(), "sync_worker", "sync_to_neon.py");
    const venvPython = path.resolve(process.cwd(), "..", ".venv", "Scripts", "python.exe");

    // Execute the sync worker once in background
    return new Promise<NextResponse>((resolve) => {
      exec(
        `"${venvPython}" "${pythonScript}" --once`,
        { cwd: path.resolve(process.cwd(), "..") },
        (error, stdout, stderr) => {
          if (error) {
            console.error("Sync trigger error:", error, stderr);
            resolve(
              NextResponse.json(
                { success: false, error: stderr || error.message },
                { status: 500 }
              )
            );
          } else {
            console.log("Sync trigger success:", stdout);
            resolve(
              NextResponse.json({
                success: true,
                message: "Sync completed successfully",
                lastSyncedAt: new Date().toISOString(),
              })
            );
          }
        }
      );
    });
  } catch (err: any) {
    return NextResponse.json({ success: false, error: err.message }, { status: 500 });
  }
}

