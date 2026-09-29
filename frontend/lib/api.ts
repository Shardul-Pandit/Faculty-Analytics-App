import { getToken, clearSession } from "./auth";
import type {
  AnalysisQuery,
  AnalysisResult,
  ColumnMapping,
  FileRecord,
  FileUploadResponse,
  MappingSuggestion,
  SavedMapping,
  TokenResponse,
  User,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

if (process.env.NODE_ENV === "development") {
  console.log("[API] Base URL:", BASE);
}

// ─── Core fetch wrapper ───────────────────────────────────────────────────────

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string>),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  const fullUrl = `${BASE}${path}`;
  if (process.env.NODE_ENV === "development") {
    console.log(`[API] → ${options.method ?? "GET"} ${fullUrl}`);
  }

  let res: Response;
  try {
    res = await fetch(fullUrl, { ...options, headers });
  } catch (networkErr) {
    // Network-level failure: server not running, CORS preflight blocked, firewall, etc.
    if (process.env.NODE_ENV === "development") {
      console.error(`[API] NETWORK ERROR on ${options.method ?? "GET"} ${fullUrl}`, networkErr);
    }
    throw new Error(
      `Cannot reach the server. Make sure the backend is running at ${BASE}`
    );
  }

  if (process.env.NODE_ENV === "development") {
    console.log(`[API] ← ${res.status} ${options.method ?? "GET"} ${fullUrl}`);
  }

  if (!res.ok) {
    // Clear stale auth and surface a clean message on 401
    if (res.status === 401) {
      clearSession();
      throw new Error("Session expired. Please sign in again.");
    }

    let detail = `Server error (HTTP ${res.status})`;
    try {
      const json = await res.json();
      detail = json.detail ?? JSON.stringify(json);
    } catch {
      // Response body wasn't JSON — keep the status-code message
    }
    if (process.env.NODE_ENV === "development") {
      console.error(`[API] ${options.method ?? "GET"} ${fullUrl} →`, res.status, detail);
    }
    throw new Error(detail);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

// ─── Auth ─────────────────────────────────────────────────────────────────────

export const api = {
  auth: {
    signup(email: string, username: string, password: string) {
      return request<TokenResponse>("/auth/signup", {
        method: "POST",
        body: JSON.stringify({ email, username, password }),
      });
    },
    login(identifier: string, password: string) {
      return request<TokenResponse>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ identifier, password }),
      });
    },
    me() {
      return request<User>("/auth/me");
    },
  },

  // ─── Files ─────────────────────────────────────────────────────────────────

  files: {
    upload(file: File, termLabel?: string) {
      const form = new FormData();
      form.append("file", file);
      if (termLabel) form.append("term_label", termLabel);
      return request<FileUploadResponse>("/files/upload", {
        method: "POST",
        body: form,
      });
    },
    list() {
      return request<FileRecord[]>("/files/list");
    },
    updateTerm(fileId: number, termLabel: string) {
      return request<FileRecord>(`/files/${fileId}/term`, {
        method: "PATCH",
        body: JSON.stringify({ term_label: termLabel }),
      });
    },
    delete(fileId: number) {
      return request<void>(`/files/${fileId}`, { method: "DELETE" });
    },
  },

  // ─── Mappings ──────────────────────────────────────────────────────────────

  mappings: {
    suggest(columns: string[]) {
      return request<MappingSuggestion>("/mappings/suggest", {
        method: "POST",
        body: JSON.stringify({ columns }),
      });
    },
    getSaved(fingerprint: string) {
      return request<SavedMapping>(`/mappings/saved/${fingerprint}`);
    },
    save(fingerprint: string, mapping: ColumnMapping) {
      return request<SavedMapping>("/mappings/save", {
        method: "POST",
        body: JSON.stringify({ columns_fingerprint: fingerprint, mapping }),
      });
    },
  },

  // ─── Analysis ──────────────────────────────────────────────────────────────

  analysis: {
    query(payload: AnalysisQuery) {
      return request<AnalysisResult>("/analysis/query", {
        method: "POST",
        body: JSON.stringify(payload),
      });
    },
    /** Authenticated download — returns a Blob so the JWT is sent correctly. */
    async downloadExcel(sessionId: string): Promise<Blob> {
      const token = getToken();
      let res: Response;
      try {
        res = await fetch(`${BASE}/analysis/export/${sessionId}`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
      } catch {
        throw new Error("Cannot reach the server. Make sure the backend is running at " + BASE);
      }
      if (res.status === 401) {
        clearSession();
        throw new Error("Session expired. Please sign in again.");
      }
      if (!res.ok) throw new Error(`Export failed (HTTP ${res.status})`);
      return res.blob();
    },
  },
};
