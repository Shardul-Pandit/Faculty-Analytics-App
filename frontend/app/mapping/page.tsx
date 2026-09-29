"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import NavBar from "@/components/NavBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { api } from "@/lib/api";
import type { ColumnMapping } from "@/lib/types";

/** Human-readable descriptions of each logical field */
const FIELD_LABELS: Record<string, { label: string; description: string; required: boolean }> = {
  student_name: { label: "Student Name",  description: "Full name of the student",          required: false },
  major:        { label: "Major",          description: "Student's academic program/major",   required: true  },
  grade:        { label: "Grade / Score",  description: "The assignment or assessment grade", required: true  },
  term:         { label: "Term/Semester",  description: "Academic term (e.g. FA24, SP25)",    required: false },
  gender:       { label: "Gender",         description: "Student gender",                     required: false },
  year:         { label: "Year/Standing",  description: "Academic year (Freshman, etc.)",     required: false },
  student_id:   { label: "Student ID",     description: "Unique student identifier",           required: false },
};

function MappingContent() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  const fileIdsParam  = searchParams.get("fileIds") ?? "";
  const columnsParam  = searchParams.get("columns") ?? "[]";
  const fileIds       = fileIdsParam.split(",").map(Number).filter(Boolean);
  const columns: string[] = JSON.parse(decodeURIComponent(columnsParam));

  const [mapping, setMapping]     = useState<ColumnMapping>({});
  const [fingerprint, setFp]      = useState("");
  const [loading, setLoading]     = useState(true);
  const [saving, setSaving]       = useState(false);
  const [error, setError]         = useState("");
  const [savedBadge, setSavedBadge] = useState(false);

  useEffect(() => {
    if (columns.length === 0) { router.push("/upload"); return; }
    loadSuggestions();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadSuggestions() {
    setLoading(true);
    try {
      const suggestion = await api.mappings.suggest(columns);
      setFp(suggestion.fingerprint);

      // Try to load a previously saved mapping for this schema
      try {
        const saved = await api.mappings.getSaved(suggestion.fingerprint);
        setMapping(saved.mapping);
      } catch {
        // No saved mapping — use the auto-detected suggestions
        setMapping(suggestion.suggestions);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load suggestions");
    } finally {
      setLoading(false);
    }
  }

  function setField(field: string, value: string) {
    setMapping((prev) => ({ ...prev, [field]: value || null }));
  }

  async function handleConfirm() {
    const missing = Object.entries(FIELD_LABELS)
      .filter(([, { required }]) => required)
      .filter(([key]) => !mapping[key])
      .map(([, { label }]) => label);

    if (missing.length > 0) {
      setError(`Please map the required field(s): ${missing.join(", ")}`);
      return;
    }

    setSaving(true);
    setError("");
    try {
      await api.mappings.save(fingerprint, mapping);
      setSavedBadge(true);
      // Navigate to analytics with context
      router.push(
        `/analytics?fileIds=${fileIds.join(",")}&mapping=${encodeURIComponent(
          JSON.stringify(mapping)
        )}`
      );
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to save mapping");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <>
        <NavBar />
        <main className="mx-auto max-w-2xl px-4 py-12 text-center text-sm text-gray-400">
          Detecting columns…
        </main>
      </>
    );
  }

  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-2xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Confirm Column Mapping</h1>
          <p className="mt-1 text-sm text-gray-500">
            We auto-detected which columns correspond to each field. Review and adjust if needed.
            Your choices are saved for future uploads with the same format.
          </p>
        </div>

        {error && <Alert type="error" message={error} className="mb-4" />}

        <Card>
          <div className="mb-4 rounded-lg bg-slate-50 px-4 py-3">
            <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
              Detected columns in your file
            </p>
            <div className="flex flex-wrap gap-2">
              {columns.map((col) => (
                <span
                  key={col}
                  className="rounded-md bg-white border border-gray-200 px-2.5 py-0.5 text-xs font-medium text-gray-700"
                >
                  {col}
                </span>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-4">
            {Object.entries(FIELD_LABELS).map(([field, { label, description, required }]) => (
              <div key={field} className="flex items-start gap-4">
                <div className="w-44 shrink-0 pt-1.5">
                  <p className="text-sm font-medium text-gray-800">
                    {label}
                    {required && <span className="ml-1 text-red-500">*</span>}
                  </p>
                  <p className="text-xs text-gray-400">{description}</p>
                </div>
                <div className="flex-1">
                  <select
                    value={mapping[field] ?? ""}
                    onChange={(e) => setField(field, e.target.value)}
                    className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                  >
                    <option value="">— not mapped —</option>
                    {columns.map((col) => (
                      <option key={col} value={col}>{col}</option>
                    ))}
                  </select>
                </div>
                {mapping[field] && (
                  <CheckCircle2 className="mt-2 h-4 w-4 shrink-0 text-green-500" />
                )}
              </div>
            ))}
          </div>
        </Card>

        <div className="mt-6 flex items-center justify-between">
          <p className="text-xs text-gray-400">
            Fields marked <span className="text-red-500">*</span> are required for analysis.
          </p>
          <Button onClick={handleConfirm} loading={saving} size="lg">
            {savedBadge ? "Saved!" : "Confirm & analyze"}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>
      </main>
    </>
  );
}

export default function MappingPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-400">Loading…</div>}>
      <MappingContent />
    </Suspense>
  );
}
