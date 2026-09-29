"use client";
import { useEffect, useState, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Send, Download, ChevronDown, ChevronUp, BarChart2, Info,
  Clock, Trophy, TrendingDown, CheckCircle2, TrendingUp,
  AlertTriangle,
} from "lucide-react";
import NavBar from "@/components/NavBar";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Alert } from "@/components/ui/Alert";
import { api } from "@/lib/api";
import { isLoggedIn, getUser } from "@/lib/auth";
import type { AnalysisResult, ColumnMapping, ComparisonCard, DataQualityNote } from "@/lib/types";

const RECENT_MAX = 5;

/** Returns a user-specific localStorage key so questions never leak between accounts. */
function recentKey(userId: number | string): string {
  return `fa_recent_questions_${userId}`;
}

function loadRecentQuestions(userId: number | string): string[] {
  if (typeof window === "undefined") return [];
  try { return JSON.parse(localStorage.getItem(recentKey(userId)) ?? "[]"); } catch { return []; }
}

function saveRecentQuestion(q: string, userId: number | string): void {
  if (typeof window === "undefined") return;
  const prev = loadRecentQuestions(userId);
  const updated = [q, ...prev.filter((x) => x !== q)].slice(0, RECENT_MAX);
  localStorage.setItem(recentKey(userId), JSON.stringify(updated));
}

function clearRecentQuestions(userId: number | string): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(recentKey(userId));
}

const EXAMPLE_QUESTIONS = [
  "Summarize the overall performance of students",
  "Which major has the highest mean grade?",
  "Compare CS vs Biology students",
  "Show the SLO attainment distribution",
  "Show grade distribution",
  "Which student performed the best?",
  "Which students improved the most?",
];

function AnalyticsContent() {
  const router       = useRouter();
  const searchParams = useSearchParams();

  const fileIdsParam = searchParams.get("fileIds") ?? "";
  const mappingParam = searchParams.get("mapping") ?? "";

  const fileIds = fileIdsParam.split(",").map(Number).filter(Boolean);

  // Resolved once on mount; never changes within a session
  const currentUser = typeof window !== "undefined" ? getUser() : null;
  const userId      = currentUser?.id ?? currentUser?.username ?? "guest";

  const [mapping, setMapping]           = useState<ColumnMapping>({});
  const [mappingReady, setMappingReady] = useState(false);
  const [question, setQuestion]         = useState("");
  const [loading, setLoading]           = useState(false);
  const [exporting, setExporting]       = useState(false);
  const [excelSuccess, setExcelSuccess] = useState(false);
  const [setupLoading, setSetupLoading] = useState(true);
  const [error, setError]               = useState("");
  const [basicMode, setBasicMode] = useState(false);
  const [result, setResult]             = useState<AnalysisResult | null>(null);
  const [testsOpen, setTestsOpen]       = useState(false);
  const [recentQuestions, setRecentQuestions] = useState<string[]>([]);

  useEffect(() => {
    if (!isLoggedIn()) { router.push("/login"); return; }
    if (fileIds.length === 0)  { router.push("/dashboard"); return; }

    setRecentQuestions(loadRecentQuestions(userId));

    if (mappingParam) {
      try {
        setMapping(JSON.parse(decodeURIComponent(mappingParam)));
        setMappingReady(true);
        setSetupLoading(false);
      } catch {
        loadMappingFromServer();
      }
    } else {
      loadMappingFromServer();
    }

    checkAI();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function checkAI() {
    try {
      const health = await fetch(
        (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000") + "/health"
      ).then((r) => r.json());
      // Use ai_configured (new); fall back to openai_configured for older backends
      const configured = health.ai_configured ?? health.openai_configured ?? false;
      setBasicMode(!configured);
    } catch {
      // Health check failed — main error will surface on query
    }
  }

  async function loadMappingFromServer() {
    setSetupLoading(true);
    try {
      const filesList  = await api.files.list();
      const firstFile  = filesList.find((f) => f.id === fileIds[0]);
      if (!firstFile) { router.push("/dashboard"); return; }

      const suggestion = await api.mappings.suggest(firstFile.detected_columns);

      try {
        const saved = await api.mappings.getSaved(suggestion.fingerprint);
        setMapping(saved.mapping);
        setMappingReady(true);
      } catch {
        router.push(
          `/mapping?fileIds=${fileIds.join(",")}&columns=${encodeURIComponent(
            JSON.stringify(firstFile.detected_columns)
          )}`
        );
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load column mapping");
    } finally {
      setSetupLoading(false);
    }
  }

  async function handleAsk(q?: string) {
    const finalQ = (q ?? question).trim();
    if (!finalQ || !mappingReady || loading) return;
    setError("");
    setLoading(true);
    setResult(null);
    setExcelSuccess(false);
    try {
      const res = await api.analysis.query({
        question: finalQ,
        file_ids: fileIds,
        mapping,
        export: true,
      });
      setResult(res);
      if (!q) setQuestion(finalQ);
      saveRecentQuestion(finalQ, userId);
      setRecentQuestions(loadRecentQuestions(userId));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Analysis failed";
      if (process.env.NODE_ENV === "development") console.error("[Analytics]", msg);
      if (msg.includes("Session expired")) { router.push("/login"); return; }
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function handleDownloadExcel(sessionId: string) {
    setExporting(true);
    setExcelSuccess(false);
    try {
      const blob = await api.analysis.downloadExcel(sessionId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "analytics_export.xlsx";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setExcelSuccess(true);
      setTimeout(() => setExcelSuccess(false), 4000);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Export failed";
      if (msg.includes("Session expired")) { router.push("/login"); return; }
      setError(msg);
    } finally {
      setExporting(false);
    }
  }

  function handleClearRecent() {
    clearRecentQuestions(userId);
    setRecentQuestions([]);
  }

  if (setupLoading) {
    return (
      <>
        <NavBar />
        <main className="mx-auto max-w-4xl px-4 py-16 text-center text-sm text-gray-400">
          Loading your data…
        </main>
      </>
    );
  }

  return (
    <>
      <NavBar />
      <main className="mx-auto max-w-5xl px-4 py-8">

        <div className="mb-6">
          <h1 className="text-2xl font-bold text-gray-900">Analytics</h1>
          <p className="mt-1 text-sm text-gray-500">
            Ask a question in plain English about your student data.
          </p>
        </div>

        {/* Basic mode banner — shown only when no AI provider is configured */}
        {basicMode && (
          <div className="mb-4 flex items-center gap-2.5 rounded-lg border border-blue-200 bg-blue-50 px-4 py-2.5 text-sm text-blue-700">
            <Info className="h-4 w-4 shrink-0 text-blue-400" />
            <span><strong>Running in basic mode.</strong></span>
          </div>
        )}

        {/* Question input */}
        <Card className="mb-6">
          <div className="flex gap-3">
            <textarea
              rows={2}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleAsk(); }
              }}
              placeholder='e.g. "Compare CS vs Biology in the after dataset"'
              className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder:text-gray-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
            />
            <Button
              onClick={() => handleAsk()}
              loading={loading}
              disabled={!question.trim() || !mappingReady}
              size="lg"
              className="self-start"
            >
              <Send className="h-4 w-4" />
              Ask
            </Button>
          </div>

          {/* Example questions */}
          <div className="mt-3 flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                disabled={loading}
                onClick={() => { setQuestion(q); handleAsk(q); }}
                className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1 text-xs text-gray-600 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {q}
              </button>
            ))}
          </div>

          {/* Recent questions */}
          {recentQuestions.length > 0 && (
            <div className="mt-4 border-t border-gray-100 pt-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="flex items-center gap-1.5 text-xs font-medium text-gray-400">
                  <Clock className="h-3.5 w-3.5" />
                  Recent
                </p>
                <button
                  onClick={handleClearRecent}
                  className="text-xs text-gray-400 hover:text-gray-600 transition-colors"
                >
                  Clear
                </button>
              </div>
              <div className="flex flex-wrap gap-2">
                {recentQuestions.map((q) => (
                  <button
                    key={q}
                    disabled={loading}
                    onClick={() => { setQuestion(q); handleAsk(q); }}
                    className="rounded-full border border-gray-200 bg-white px-3 py-1 text-xs text-gray-500 hover:border-indigo-300 hover:bg-indigo-50 hover:text-indigo-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>

        {error && <Alert type="error" message={error} className="mb-4" />}

        {loading && (
          <div className="flex flex-col items-center justify-center gap-3 py-16 text-gray-400">
            <BarChart2 className="h-8 w-8 animate-pulse text-indigo-300" />
            <p className="text-sm">Analyzing student data…</p>
          </div>
        )}

        {result && !loading && (
          <div className="flex flex-col gap-6">

            {/* NL Summary */}
            <Card>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-semibold text-gray-900">Summary</h2>
                {result.export_session_id && (
                  <div className="flex items-center gap-2.5">
                    {excelSuccess && (
                      <span className="flex items-center gap-1 text-xs text-green-600">
                        <CheckCircle2 className="h-3.5 w-3.5" />
                        Downloaded
                      </span>
                    )}
                    <button
                      onClick={() => handleDownloadExcel(result.export_session_id!)}
                      disabled={exporting}
                      className="flex items-center gap-1.5 rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Download className="h-3.5 w-3.5" />
                      {exporting ? "Generating report…" : "Download Excel"}
                    </button>
                  </div>
                )}
              </div>
              <p className="border-l-4 border-indigo-200 pl-3 text-sm leading-relaxed text-gray-700">
                {result.summary}
              </p>

            </Card>

            {/* Data quality notes */}
            {result.data_quality_notes && result.data_quality_notes.length > 0 && (
              <DataQualityCard notes={result.data_quality_notes} />
            )}

            {/* Major-vs-major comparison cards */}
            {result.comparison_cards && result.comparison_cards.length === 2 && (
              <MajorComparisonCards cards={result.comparison_cards} />
            )}

            {/* Charts — single column on mobile, 2 cols on large screens */}
            {result.charts && result.charts.length > 0 && (
              <div>
                <SectionHeading>Charts</SectionHeading>
                <div className={result.charts.length === 1
                  ? "grid grid-cols-1"
                  : "grid grid-cols-1 lg:grid-cols-2 gap-4"
                }>
                  {result.charts.map((chart, i) => (
                    <Card key={i} className="overflow-hidden p-0">
                      <div className="border-b border-gray-100 bg-gray-50/60 px-4 py-2.5">
                        <p className="text-sm font-medium text-gray-700">{chart.title}</p>
                      </div>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={`data:image/png;base64,${chart.image_b64}`}
                        alt={chart.title}
                        className="w-full"
                        style={{ minHeight: "220px", display: "block" }}
                      />
                    </Card>
                  ))}
                </div>
              </div>
            )}

            {/* Tables */}
            {result.tables && result.tables.length > 0 && (
              <div>
                <SectionHeading>Data Tables</SectionHeading>
                <div className="flex flex-col gap-4">
                  {result.tables.map((table, i) => {
                    const isStudentTable =
                      table.title === "Top Students" || table.title === "Bottom Students";
                    const isChangeTable =
                      table.title === "Top Improvers" || table.title === "Biggest Declines";

                    if (isStudentTable) {
                      return (
                        <StudentRankingTable
                          key={i}
                          title={table.title}
                          rows={table.rows}
                          isTop={table.title === "Top Students"}
                        />
                      );
                    }
                    if (isChangeTable) {
                      return (
                        <GradeChangeTable
                          key={i}
                          title={table.title}
                          rows={table.rows}
                          isImprovers={table.title === "Top Improvers"}
                        />
                      );
                    }
                    return (
                      <Card key={i} padding={false}>
                        <div className="border-b border-gray-100 bg-gray-50/60 px-4 py-2.5">
                          <p className="text-sm font-medium text-gray-700">{table.title}</p>
                        </div>
                        <div className="overflow-x-auto">
                          <DataTable rows={table.rows} />
                        </div>
                      </Card>
                    );
                  })}
                </div>
              </div>
            )}

            {/* Statistical tests (collapsible) */}
            {result.stat_tests && result.stat_tests.length > 0 && (
              <Card padding={false}>
                <button
                  onClick={() => setTestsOpen((o) => !o)}
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                >
                  <span className="font-semibold text-gray-900">Statistical Tests</span>
                  {testsOpen
                    ? <ChevronUp className="h-4 w-4 text-gray-500" />
                    : <ChevronDown className="h-4 w-4 text-gray-500" />}
                </button>
                {testsOpen && (
                  <div className="overflow-x-auto border-t border-gray-100">
                    <DataTable rows={result.stat_tests as Record<string, unknown>[]} />
                  </div>
                )}
              </Card>
            )}

          </div>
        )}
      </main>
    </>
  );
}

// ─── Data quality card ────────────────────────────────────────────────────────

function DataQualityCard({ notes }: { notes: DataQualityNote[] }) {
  const hasWarnings = notes.some((n) => n.level === "warning");
  return (
    <Card padding={false} className={`border-t-4 ${hasWarnings ? "border-amber-400" : "border-emerald-400"}`}>
      <div className={`flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 ${hasWarnings ? "bg-amber-50/40" : "bg-emerald-50/40"}`}>
        {hasWarnings
          ? <AlertTriangle className="h-4 w-4 text-amber-500" />
          : <CheckCircle2 className="h-4 w-4 text-emerald-500" />
        }
        <p className="text-sm font-semibold text-gray-800">Data Quality Notes</p>
      </div>
      <ul className="flex flex-col gap-1.5 px-4 py-3">
        {notes.map((note, i) => (
          <li
            key={i}
            className={`flex items-start gap-2 text-xs leading-relaxed ${
              note.level === "warning" ? "text-amber-800" : "text-emerald-700"
            }`}
          >
            <span className="mt-0.5 shrink-0 font-bold">
              {note.level === "warning" ? "⚠" : "✓"}
            </span>
            <span>{note.message}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ─── Grade change table ───────────────────────────────────────────────────────

function GradeChangeTable({
  title,
  rows,
  isImprovers,
}: {
  title: string;
  rows: Record<string, unknown>[];
  isImprovers: boolean;
}) {
  if (!rows || rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  const Icon = isImprovers ? TrendingUp : TrendingDown;
  const accentClass = isImprovers ? "border-emerald-400" : "border-rose-400";
  const iconClass   = isImprovers ? "text-emerald-500"   : "text-rose-500";
  const bgClass     = isImprovers ? "bg-emerald-50/40"   : "bg-rose-50/40";
  const headerBg    = isImprovers ? "bg-emerald-50"      : "bg-rose-50";
  const headerText  = isImprovers ? "text-emerald-700"   : "text-rose-700";

  return (
    <Card padding={false} className={`border-t-4 ${accentClass}`}>
      <div className={`flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 ${bgClass}`}>
        <Icon className={`h-4 w-4 ${iconClass}`} />
        <p className="text-sm font-semibold text-gray-800">{title}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={headerBg}>
              {cols.map((col) => (
                <th
                  key={col}
                  className={`whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide ${headerText}`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr
                key={i}
                className="border-t border-gray-100 transition-colors hover:bg-gray-50"
              >
                {cols.map((col) => {
                  const val = row[col];
                  if (col === "Change" && typeof val === "number") {
                    const isPos = val >= 0;
                    return (
                      <td key={col} className="whitespace-nowrap px-4 py-2.5">
                        <span className={`font-semibold ${isPos ? "text-emerald-600" : "text-rose-600"}`}>
                          {isPos ? "+" : ""}{val.toFixed(1)}
                        </span>
                      </td>
                    );
                  }
                  return (
                    <td key={col} className="whitespace-nowrap px-4 py-2.5 text-gray-700">
                      {formatCell(val, col)}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ─── Student ranking table ────────────────────────────────────────────────────

const RANK_MEDALS: Record<number, string> = { 1: "🥇", 2: "🥈", 3: "🥉" };

function StudentRankingTable({
  title,
  rows,
  isTop,
}: {
  title: string;
  rows: Record<string, unknown>[];
  isTop: boolean;
}) {
  if (!rows || rows.length === 0) return null;
  const cols = Object.keys(rows[0]);
  const Icon = isTop ? Trophy : TrendingDown;
  const accentClass = isTop ? "border-amber-400" : "border-rose-400";
  const iconClass   = isTop ? "text-amber-500"   : "text-rose-500";
  const bgClass     = isTop ? "bg-amber-50/40"   : "bg-rose-50/40";

  return (
    <Card padding={false} className={`border-t-4 ${accentClass}`}>
      <div className={`flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 ${bgClass}`}>
        <Icon className={`h-4 w-4 ${iconClass}`} />
        <p className="text-sm font-semibold text-gray-800">{title}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={isTop ? "bg-amber-50" : "bg-rose-50"}>
              {cols.map((col) => (
                <th
                  key={col}
                  className={`whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide ${
                    isTop ? "text-amber-700" : "text-rose-700"
                  }`}
                >
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const rank = typeof row["Rank"] === "number" ? row["Rank"] : i + 1;
              const medal = RANK_MEDALS[rank as number];
              return (
                <tr
                  key={i}
                  className={`border-t border-gray-100 transition-colors hover:bg-gray-50 ${
                    rank === 1 ? (isTop ? "bg-amber-50/60 font-medium" : "bg-rose-50/60 font-medium") : ""
                  }`}
                >
                  {cols.map((col) => (
                    <td key={col} className="whitespace-nowrap px-4 py-2.5 text-gray-700">
                      {col === "Rank" && medal
                        ? `${medal} ${rank}`
                        : formatCell(row[col], col)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

// ─── Section heading ──────────────────────────────────────────────────────────

function SectionHeading({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <span className="h-4 w-1 rounded-full bg-indigo-400" />
      <h2 className="font-semibold text-gray-900">{children}</h2>
    </div>
  );
}

// ─── Major comparison metric cards ────────────────────────────────────────────

function MajorComparisonCards({ cards }: { cards: ComparisonCard[] }) {
  const [a, b] = cards;
  const diff = (a.mean != null && b.mean != null)
    ? (a.mean - b.mean).toFixed(2)
    : null;
  const diffNum = diff != null ? parseFloat(diff) : null;

  return (
    <div>
      <SectionHeading>Major Comparison</SectionHeading>
      <div className="grid gap-4 sm:grid-cols-2">
        {cards.map((card) => (
          <Card key={card.label} className="border-t-4 border-indigo-400">
            <p className="mb-3 text-base font-bold text-gray-900">{card.label}</p>
            <div className="grid grid-cols-2 gap-3">
              <MetricCell label="Mean Grade"  value={card.mean?.toFixed(2) ?? "—"} highlight />
              <MetricCell label="Median Grade" value={card.median?.toFixed(2) ?? "—"} />
              <MetricCell label="Students (N)" value={card.n?.toString() ?? "—"} />
              <MetricCell
                label="Meet or Exceed SLO"
                value={card.meet_exceed_pct != null ? `${card.meet_exceed_pct.toFixed(0)}%` : "—"}
              />
            </div>
          </Card>
        ))}
      </div>
      {diffNum != null && (
        <p className="mt-3 text-center text-sm text-gray-500">
          Mean grade difference:{" "}
          <span className={`font-semibold ${diffNum > 0 ? "text-indigo-600" : diffNum < 0 ? "text-rose-500" : "text-gray-600"}`}>
            {diffNum > 0 ? "+" : ""}{diff} points
          </span>{" "}
          ({a.label} vs {b.label})
        </p>
      )}
    </div>
  );
}

function MetricCell({ label, value, highlight }: { label: string; value: string; highlight?: boolean }) {
  return (
    <div className="rounded-lg bg-gray-50 px-3 py-2.5">
      <p className="text-xs text-gray-400">{label}</p>
      <p className={`mt-0.5 font-bold ${highlight ? "text-xl text-indigo-700" : "text-base text-gray-800"}`}>
        {value}
      </p>
    </div>
  );
}

// ─── Generic data table ───────────────────────────────────────────────────────

function DataTable({ rows }: { rows: Record<string, unknown>[] }) {
  if (!rows || rows.length === 0) return null;
  const cols = Object.keys(rows[0]);

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="bg-indigo-50">
          {cols.map((col) => (
            <th
              key={col}
              className="whitespace-nowrap px-4 py-2.5 text-left text-xs font-semibold uppercase tracking-wide text-indigo-700"
            >
              {col}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr
            key={i}
            className={`border-t border-gray-100 transition-colors hover:bg-indigo-50/30 ${
              i % 2 === 1 ? "bg-gray-50/50" : ""
            }`}
          >
            {cols.map((col) => (
              <td key={col} className="whitespace-nowrap px-4 py-2.5 text-gray-700">
                {formatCell(row[col], col)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

// Columns that hold decimal values. JSON drops trailing zeros (62.0 arrives as 62),
// so these are formatted by column name rather than by Number.isInteger().
const DECIMAL_COLS = /grade|mean|median|^sd$|^min$|^max$/i;

function formatCell(val: unknown, col?: string): string {
  if (val === null || val === undefined) return "—";
  if (typeof val === "boolean") return val ? "Yes ✓" : "No";
  if (typeof val === "number") {
    if (col?.includes("%")) return val.toFixed(1);
    if (col && DECIMAL_COLS.test(col)) return val.toFixed(2);
    return Number.isInteger(val) ? String(val) : val.toFixed(2);
  }
  return String(val);
}

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<div className="p-8 text-sm text-gray-400">Loading…</div>}>
      <AnalyticsContent />
    </Suspense>
  );
}
