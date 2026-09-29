// ─── Auth ────────────────────────────────────────────────────────────────────

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  username: string;
}

export interface User {
  id: number;
  email: string;
  username: string;
}

// ─── Files ───────────────────────────────────────────────────────────────────

export interface FileRecord {
  id: number;
  original_filename: string;
  stored_filename: string;
  term_label: string | null;
  detected_columns: string[];
  row_count: number;
  upload_time: string;
}

export interface FileUploadResponse {
  file_id: number;
  original_filename: string;
  detected_columns: string[];
  row_count: number;
  term_label: string | null;
}

// ─── Mappings ─────────────────────────────────────────────────────────────────

/** Keys are logical names; values are actual CSV column names or null. */
export type ColumnMapping = Record<string, string | null>;

export interface MappingSuggestion {
  columns: string[];
  suggestions: ColumnMapping;
  fingerprint: string;
}

export interface SavedMapping {
  id: number;
  columns_fingerprint: string;
  mapping: ColumnMapping;
}

// ─── Analysis ─────────────────────────────────────────────────────────────────

export interface DataQualityNote {
  level: "warning" | "ok";
  message: string;
}

export interface AnalysisQuery {
  question: string;
  file_ids: number[];
  mapping: ColumnMapping;
  export?: boolean;
}

export interface TableData {
  title: string;
  rows: Record<string, unknown>[];
}

export interface ChartData {
  title: string;
  image_b64: string;
}

export interface ComparisonCard {
  label: string;
  mean: number | null;
  median: number | null;
  n: number | null;
  meet_exceed_pct: number | null;
}

export interface AnalysisResult {
  summary: string;
  /** Data quality warnings or all-clear note. */
  data_quality_notes: DataQualityNote[] | null;
  tables: TableData[] | null;
  charts: ChartData[] | null;
  stat_tests: Record<string, unknown>[] | null;
  export_session_id: string | null;
  raw_intent: Record<string, unknown> | null;
  comparison_cards: ComparisonCard[] | null;
}
