"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  FileText, Trash2, Upload, BarChart2, Calendar, Database,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { api } from "@/lib/api";
import { isLoggedIn } from "@/lib/auth";
import type { FileRecord } from "@/lib/types";

export default function DashboardPage() {
  const router = useRouter();
  const [files, setFiles]   = useState<FileRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState("");

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }
    loadFiles();
  }, [router]);

  async function loadFiles() {
    setLoading(true);
    try {
      const data = await api.files.list();
      setFiles(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load files");
    } finally {
      setLoading(false);
    }
  }

  async function deleteFile(id: number, name: string) {
    if (!confirm(`Delete "${name}"? This cannot be undone.`)) return;
    try {
      await api.files.delete(id);
      setFiles((prev) => prev.filter((f) => f.id !== id));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to delete file");
    }
  }

  const canAnalyze = files.length >= 1;

  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-6xl px-4 py-8">

        {/* Header */}
        <div className="mb-8 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
            <p className="mt-1 text-sm text-gray-500">
              Upload 1 or 2 CSV files, then ask questions about your student data.
            </p>
          </div>
          <Link href="/upload">
            <Button>
              <Upload className="h-4 w-4" />
              Upload CSV
            </Button>
          </Link>
        </div>

        {error && <Alert type="error" message={error} className="mb-6" />}

        {/* Stats row */}
        <div className="mb-6 grid grid-cols-2 gap-4 sm:grid-cols-3">
          <Card className="flex items-center gap-4">
            <div className="rounded-lg bg-indigo-50 p-2.5">
              <Database className="h-5 w-5 text-indigo-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">{files.length}</p>
              <p className="text-xs text-gray-500">Files uploaded</p>
            </div>
          </Card>
          <Card className="flex items-center gap-4">
            <div className="rounded-lg bg-green-50 p-2.5">
              <BarChart2 className="h-5 w-5 text-green-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">
                {files.reduce((s, f) => s + (f.row_count ?? 0), 0)}
              </p>
              <p className="text-xs text-gray-500">Total student records</p>
            </div>
          </Card>
          <Card className="flex items-center gap-4 col-span-2 sm:col-span-1">
            <div className="rounded-lg bg-amber-50 p-2.5">
              <Calendar className="h-5 w-5 text-amber-600" />
            </div>
            <div>
              <p className="text-2xl font-bold text-gray-900">
                {files.filter((f) => f.term_label).length}
              </p>
              <p className="text-xs text-gray-500">Files with term labels</p>
            </div>
          </Card>
        </div>

        {/* File list */}
        <Card padding={false}>
          <div className="flex items-center justify-between border-b border-gray-100 px-6 py-4">
            <h2 className="font-semibold text-gray-900">Your Files</h2>
            {canAnalyze && (
              // Pass actual file IDs so the analytics page doesn't redirect back
              <Link href={`/analytics?fileIds=${files.map((f) => f.id).join(",")}`}>
                <Button size="sm">
                  <BarChart2 className="h-4 w-4" />
                  Analyze
                </Button>
              </Link>
            )}
          </div>

          {loading ? (
            <div className="flex items-center justify-center py-16 text-sm text-gray-400">
              Loading…
            </div>
          ) : files.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-3 py-16">
              <FileText className="h-10 w-10 text-gray-300" />
              <p className="text-sm text-gray-500">No files yet.</p>
              <Link href="/upload">
                <Button variant="secondary" size="sm">Upload your first CSV</Button>
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-gray-100">
              {files.map((file) => (
                <li
                  key={file.id}
                  className="flex items-center justify-between px-6 py-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="rounded-lg bg-indigo-50 p-2">
                      <FileText className="h-4 w-4 text-indigo-600" />
                    </div>
                    <div className="min-w-0">
                      <p className="truncate font-medium text-gray-900">
                        {file.original_filename}
                      </p>
                      <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                        <span>{file.row_count?.toLocaleString()} rows</span>
                        <span>·</span>
                        <span>{file.detected_columns?.length} columns</span>
                        {file.term_label && (
                          <>
                            <span>·</span>
                            <span className="rounded bg-indigo-50 px-1.5 py-0.5 text-indigo-700 font-medium">
                              {file.term_label}
                            </span>
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => deleteFile(file.id, file.original_filename)}
                    className="ml-4 shrink-0 rounded-lg p-1.5 text-gray-400 hover:bg-red-50 hover:text-red-500 transition-colors"
                    title="Delete file"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>

        {/* Workflow hint */}
        {files.length > 0 && files.length < 2 && (
          <p className="mt-4 text-center text-sm text-gray-400">
            Tip: Upload a second file to enable before/after comparisons.
          </p>
        )}

      </main>
    </>
  );
}
