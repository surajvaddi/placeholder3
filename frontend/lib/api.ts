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

export type ParentSeed = {
  seed_id: string;
  name: string;
  category: string;
  seed_type: string;
  source_url: string;
  aliases: string[];
  enabled: boolean;
  priority: number;
  source_hints: string[];
  tags: string[];
  notes: string;
  updated_at: string;
};

export type ExpansionSeed = {
  seed_id: string;
  connector: string;
  source_url: string;
  applies_to: {
    categories: string[];
    seed_types: string[];
    seed_ids: string[];
    tags: string[];
  };
  enabled: boolean;
  priority: number;
  discovery_mode: string;
  host_patterns: string[];
  source_hints: string[];
  limits: {
    max_requests_per_parent: number;
    max_results_per_parent: number;
  };
  notes: string;
  updated_at: string;
};

export type SeedBundle = {
  parent_seeds: ParentSeed[];
  expansion_seeds: ExpansionSeed[];
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

export async function getSeeds(): Promise<SeedBundle> {
  const res = await fetch(`${API_BASE}/seeds`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Unable to load seeds.");
  }
  return res.json();
}

export function exportCsvUrl(runId: number): string {
  return `${API_BASE}/runs/${runId}/export`;
}
