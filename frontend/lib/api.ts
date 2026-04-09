export type Run = {
  run_id: number;
  run_name: string;
  status: string;
  parent_entity_count: number;
  discovered_club_count: number;
  deduped_count: number;
  notes: string;
};

const API_BASE = "http://localhost:8000";

export async function listRuns(): Promise<Run[]> {
  const res = await fetch(`${API_BASE}/runs`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error("Unable to load runs.");
  }
  return res.json();
}

export async function createRun(runName: string, notes: string): Promise<Run> {
  const res = await fetch(`${API_BASE}/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ run_name: runName, notes })
  });
  if (!res.ok) {
    throw new Error("Unable to create run.");
  }
  return res.json();
}

export function exportCsvUrl(runId: number): string {
  return `${API_BASE}/runs/${runId}/export`;
}
