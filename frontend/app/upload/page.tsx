"use client";
import { useState, useRef } from "react";
import { useRouter } from "next/navigation";
import { Upload, FileText, X, ArrowRight, FlaskConical } from "lucide-react";
import { clsx } from "clsx";
import NavBar from "@/components/NavBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Alert } from "@/components/ui/Alert";
import { api } from "@/lib/api";

interface FileSlot {
  file: File;
  termLabel: string;
}

export default function UploadPage() {
  const router = useRouter();
  const [slots, setSlots]     = useState<(FileSlot | null)[]>([null, null]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");
  const inputRefs             = [useRef<HTMLInputElement>(null), useRef<HTMLInputElement>(null)];

  function pickFile(idx: number, file: File) {
    if (!file.name.toLowerCase().endsWith(".csv")) {
      setError("Only CSV files are supported right now.");
      return;
    }
    setError("");
    setSlots((prev) => {
      const next = [...prev];
      next[idx] = { file, termLabel: "" };
      return next;
    });
  }

  function removeFile(idx: number) {
    setSlots((prev) => {
      const next = [...prev];
      next[idx] = null;
      return next;
    });
  }

  function setTermLabel(idx: number, value: string) {
    setSlots((prev) => {
      const next = [...prev];
      if (next[idx]) next[idx] = { ...next[idx]!, termLabel: value };
      return next;
    });
  }

  function onDrop(idx: number, e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) pickFile(idx, file);
  }

  async function handleUpload() {
    const toUpload = slots.filter(Boolean) as FileSlot[];
    if (toUpload.length === 0) { setError("Please select at least one CSV file."); return; }
    setError("");
    setLoading(true);
    try {
      const uploadedIds: number[] = [];
      for (const slot of toUpload) {
        const res = await api.files.upload(slot.file, slot.termLabel || undefined);
        uploadedIds.push(res.file_id);
      }
      // Go to mapping confirmation with the first uploaded file's columns
      const firstRes = await api.files.list();
      const firstFile = firstRes.find((f) => f.id === uploadedIds[0]);
      if (firstFile?.detected_columns) {
        router.push(
          `/mapping?fileIds=${uploadedIds.join(",")}&columns=${encodeURIComponent(
            JSON.stringify(firstFile.detected_columns)
          )}`
        );
      } else {
        router.push("/dashboard");
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Upload failed");
    } finally {
      setLoading(false);
    }
  }

  const hasFiles = slots.some(Boolean);

  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-2xl px-4 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Upload CSV Files</h1>
          <p className="mt-1 text-sm text-gray-500">
            Upload 1 file for a single-term analysis, or 2 files to compare before and after.
          </p>
        </div>

        {/* Sample data hint */}
        <div className="mb-5 rounded-lg border border-indigo-100 bg-indigo-50/60 px-4 py-3 text-sm text-indigo-800">
          <div className="flex items-start gap-3">
            <FlaskConical className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
            <span>
              <strong>Trying the app for the first time?</strong> Download the sample CSV files below
              and upload them to explore the app.
            </span>
          </div>
          <div className="mt-3 ml-7 flex flex-wrap gap-2">
            <a
              href="/samples/assessment_before.csv"
              download
              className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 transition-colors"
            >
              ↓ Sample file 1
            </a>
            <a
              href="/samples/assessment_after.csv"
              download
              className="inline-flex items-center gap-1.5 rounded-md border border-indigo-200 bg-white px-3 py-1.5 text-xs font-medium text-indigo-700 hover:bg-indigo-50 transition-colors"
            >
              ↓ Sample file 2
            </a>
          </div>
        </div>

        {error && <Alert type="error" message={error} className="mb-4" />}

        <div className="flex flex-col gap-4">
          {[0, 1].map((idx) => (
          <FileDropZone
            key={idx}
            label={idx === 0 ? "File 1" : "File 2 (optional)"}
            slot={slots[idx]}
              inputRef={inputRefs[idx]}
              onDrop={(e) => onDrop(idx, e)}
              onPick={(f) => pickFile(idx, f)}
              onRemove={() => removeFile(idx)}
              onTermChange={(v) => setTermLabel(idx, v)}
            />
          ))}
        </div>

        <div className="mt-6 flex justify-end">
          <Button
            onClick={handleUpload}
            loading={loading}
            disabled={!hasFiles}
            size="lg"
          >
            {loading ? "Uploading files…" : "Upload & configure columns"}
            <ArrowRight className="h-4 w-4" />
          </Button>
        </div>

        <p className="mt-3 text-center text-xs text-gray-400">
          Files are stored securely on the server and linked to your account.
        </p>
      </main>
    </>
  );
}

// ─── File drop zone sub-component ────────────────────────────────────────────

interface DropZoneProps {
  label: string;
  slot: FileSlot | null;
  inputRef: React.RefObject<HTMLInputElement | null>;
  onDrop: (e: React.DragEvent) => void;
  onPick: (f: File) => void;
  onRemove: () => void;
  onTermChange: (v: string) => void;
}

function FileDropZone({
  label, slot, inputRef, onDrop, onPick, onRemove, onTermChange,
}: DropZoneProps) {
  const [dragging, setDragging] = useState(false);

  return (
    <Card>
      <p className="mb-3 text-sm font-medium text-gray-700">{label}</p>

      {slot ? (
        <div className="flex flex-col gap-3">
          {/* Selected file */}
          <div className="flex items-center gap-3 rounded-lg bg-indigo-50 px-4 py-3">
            <FileText className="h-5 w-5 shrink-0 text-indigo-600" />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium text-gray-900">{slot.file.name}</p>
              <p className="text-xs text-gray-500">
                {(slot.file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            <button
              onClick={onRemove}
              className="rounded p-1 text-gray-400 hover:text-red-500 transition-colors"
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          {/* Term label */}
          <Input
            label='File label (optional, e.g. "FA24" or "SP25")'
            placeholder="FA24"
            value={slot.termLabel}
            onChange={(e) => onTermChange(e.target.value)}
          />
        </div>
      ) : (
        <div
          onDrop={onDrop}
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onClick={() => inputRef.current?.click()}
          className={clsx(
            "flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed py-10 transition-colors",
            dragging
              ? "border-indigo-400 bg-indigo-50"
              : "border-gray-200 hover:border-indigo-300 hover:bg-slate-50"
          )}
        >
          <Upload className="h-8 w-8 text-gray-300" />
          <p className="text-sm text-gray-500">
            Drag & drop a CSV, or{" "}
            <span className="text-indigo-600 font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-400">CSV files only</p>
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => { if (e.target.files?.[0]) onPick(e.target.files[0]); }}
          />
        </div>
      )}
    </Card>
  );
}
