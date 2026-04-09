export type Run = {
  run_id: number;
  run_name: string;
  status: string;
  run_mode: "full" | "incremental" | "seed_targeted";
  parent_entity_count: number;
  discovered_club_count: number;
  deduped_count: number;
  notes: string;
};

export type RunDiagnostics = {
  summary: {
    record_count: number;
    review_count: number;
    average_confidence: number;
    rejected_count: number;
    log_count: number;
  };
  logs: Array<{
    shot: string;
    unit_key: string;
    seed_id: string;
    expansion_seed_id: string;
    status: string;
    input_fingerprint: string;
    started_at: string;
    completed_at: string | null;
    error_message: string;
    context: Record<string, unknown>;
  }>;
  records: Array<{
    parent_key: string;
    expansion_seed_id: string;
    email: string;
    name: string;
    business_name: string;
    category: string;
    location: string;
    city: string;
    state: string;
    followers: string;
    website: string;
    instagram: string;
    confidence_score: number;
    review_flags: string[];
    evidence_count: number;
    source_count: number;
    notes: string;
    status: string;
  }>;
};

const API_BASE = "http://localhost:8000";

export async function listRuns(): Promise<Run[]> {
  const res = await fetch(`${API_BASE}/runs`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Unable to load runs.");
  }
  return res.json();
}

export async function createRun(
  runName: string,
  notes: string,
  mode: Run["run_mode"],
  seedIds: string[]
): Promise<Run> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_name: runName, notes, mode, seed_ids: seedIds })
  });
  if (!res.ok) {
    throw new Error("Unable to create run.");
  }
  return res.json();
}

export async function getRunDiagnostics(runId: number): Promise<RunDiagnostics> {
  const res = await fetch(`${API_BASE}/runs/${runId}/diagnostics`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Unable to load run diagnostics.");
  }
  return res.json();
}

export function exportCsvUrl(runId: number): string {
  return `${API_BASE}/runs/${runId}/export`;
}
