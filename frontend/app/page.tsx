"use client";

import { useEffect, useState } from "react";
import {
  createRun,
  exportCsvUrl,
  getRunDiagnostics,
  getSeeds,
  listRuns,
  Run,
  RunDiagnostics,
  SeedBundle
} from "../lib/api";

type SeedReference = {
  seed_id: string;
  name: string;
  family: "parent" | "expansion";
  source_url: string;
  details: string;
};

type ShotSummary = {
  shot: string;
  totalUnits: number;
  completedUnits: number;
  failedUnits: number;
  activeUnits: number;
  discoveredCount: number;
  acceptedCount: number;
  rejectedCount: number;
};

function parseSelectedSeedIds(seedIds: string): string[] {
  return seedIds
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean);
}

function toSeedReferences(bundle: SeedBundle | null, selectedSeedIds: string[]): SeedReference[] {
  if (!bundle) {
    return [];
  }

  const parentReferences = bundle.parent_seeds.map((seed) => ({
    seed_id: seed.seed_id,
    name: seed.name,
    family: "parent" as const,
    source_url: seed.source_url,
    details: `${seed.category} • ${seed.seed_type}`
  }));
  const expansionReferences = bundle.expansion_seeds.map((seed) => ({
    seed_id: seed.seed_id,
    name: seed.seed_id,
    family: "expansion" as const,
    source_url: seed.source_url,
    details: `${seed.connector} • ${seed.discovery_mode}`
  }));
  const index = new Map(
    [...parentReferences, ...expansionReferences].map((seed) => [seed.seed_id.toLowerCase(), seed])
  );

  return selectedSeedIds.flatMap((seedId) => {
    const resolved = index.get(seedId.toLowerCase());
    if (!resolved) {
      return [
        {
          seed_id: seedId,
          name: seedId,
          family: "expansion" as const,
          source_url: "",
          details: "Seed not found in current bundle"
        }
      ];
    }
    return [resolved];
  });
}

function toNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function summarizeShot(
  shot: string,
  logs: RunDiagnostics["logs"]
): ShotSummary {
  const shotLogs = logs.filter((log) => log.shot === shot);

  return shotLogs.reduce<ShotSummary>(
    (summary, log) => {
      const normalizedStatus = log.status.toLowerCase();
      const isFailed = normalizedStatus === "failed" || normalizedStatus === "error";
      const isCompleted =
        normalizedStatus === "completed" ||
        normalizedStatus === "success" ||
        (!!log.completed_at && !isFailed);
      const isActive = !isCompleted && !isFailed;
      const context = log.context ?? {};

      return {
        shot,
        totalUnits: summary.totalUnits + 1,
        completedUnits: summary.completedUnits + (isCompleted ? 1 : 0),
        failedUnits: summary.failedUnits + (isFailed ? 1 : 0),
        activeUnits: summary.activeUnits + (isActive ? 1 : 0),
        discoveredCount:
          summary.discoveredCount +
          toNumber(context.discovered_count) +
          toNumber(context.discovered_club_count),
        acceptedCount:
          summary.acceptedCount +
          toNumber(context.accepted_count) +
          toNumber(context.parent_entity_count) +
          toNumber(context.persisted_count),
        rejectedCount:
          summary.rejectedCount +
          toNumber(context.rejected_count) +
          toNumber(context.dedupe_pairs_removed)
      };
    },
    {
      shot,
      totalUnits: 0,
      completedUnits: 0,
      failedUnits: 0,
      activeUnits: 0,
      discoveredCount: 0,
      acceptedCount: 0,
      rejectedCount: 0
    }
  );
}

function formatShotLabel(shot: string): string {
  return shot === "shot1" ? "Shot 1" : shot === "shot2" ? "Shot 2" : shot;
}

export default function HomePage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runName, setRunName] = useState("initial-two-shot");
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState<Run["run_mode"]>("seed_targeted");
  const [seedIds, setSeedIds] = useState("parent_sacnas,expand_sacnas_chapter_directory");
  const [seedBundle, setSeedBundle] = useState<SeedBundle | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [diagnostics, setDiagnostics] = useState<RunDiagnostics | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);

  const selectedSeedIds = parseSelectedSeedIds(seedIds);
  const seedReferences = toSeedReferences(seedBundle, selectedSeedIds);
  const shotSummaries = diagnostics
    ? [summarizeShot("shot1", diagnostics.logs), summarizeShot("shot2", diagnostics.logs)]
    : [];

  async function refreshRuns() {
    try {
      setRuns(await listRuns());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }

  useEffect(() => {
    async function loadInitialData() {
      try {
        const [runList, seeds] = await Promise.all([listRuns(), getSeeds()]);
        setRuns(runList);
        setSeedBundle(seeds);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Unknown error");
      }
    }

    loadInitialData();
  }, []);

  async function loadDiagnostics(runId: number) {
    setDiagnosticsLoading(true);
    setSelectedRunId(runId);
    try {
      setDiagnostics(await getRunDiagnostics(runId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setDiagnosticsLoading(false);
    }
  }

  async function onCreateRun() {
    setLoading(true);
    setError("");
    try {
      const run = await createRun(runName, notes, mode, selectedSeedIds);
      await refreshRuns();
      await loadDiagnostics(run.run_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="container">
      <h1>Collegiate Prospecting Dashboard</h1>
      <p className="subtitle">
        Run the two-shot workflow, inspect seed coverage, and review scraped clubs before export.
      </p>

      <section className="card">
        <h2>Start New Run</h2>
        <label>
          Run name
          <input value={runName} onChange={(e) => setRunName(e.target.value)} />
        </label>
        <label>
          Notes
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
        </label>
        <label>
          Run mode
          <select value={mode} onChange={(e) => setMode(e.target.value as Run["run_mode"])}>
            <option value="seed_targeted">Seed targeted</option>
            <option value="incremental">Incremental</option>
            <option value="full">Full</option>
          </select>
        </label>
        <label>
          Seed IDs
          <input
            value={seedIds}
            onChange={(e) => setSeedIds(e.target.value)}
            placeholder="Comma-separated seed IDs"
          />
        </label>
        <button onClick={onCreateRun} disabled={loading || runName.trim().length < 2}>
          {loading ? "Running..." : "Start Two-Shot Run"}
        </button>
        {error ? <p className="error">{error}</p> : null}
      </section>

      <section className="grid">
        <article className="card">
          <h2>Seed Links</h2>
          <p className="subtitle">
            The current seed selection resolves against the backend seed bundle.
          </p>
          {seedReferences.length === 0 ? (
            <p>No seed IDs selected.</p>
          ) : (
            <ul className="seed-list">
              {seedReferences.map((seed) => (
                <li key={`${seed.family}-${seed.seed_id}`}>
                  <div className="seed-head">
                    <span className="pill">{seed.family}</span>
                    <code>{seed.seed_id}</code>
                  </div>
                  <strong>{seed.name}</strong>
                  <p className="muted">{seed.details}</p>
                  {seed.source_url ? (
                    <a href={seed.source_url} target="_blank" rel="noreferrer">
                      {seed.source_url}
                    </a>
                  ) : (
                    <span className="muted">No source URL attached to this seed.</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </article>

        <article className="card">
          <h2>Shot Progress</h2>
          {!diagnostics ? (
            <p>Select a run to inspect shot-level progress.</p>
          ) : (
            <div className="metric-grid">
              {shotSummaries.map((summary) => (
                <div className="metric-card" key={summary.shot}>
                  <h3>{formatShotLabel(summary.shot)}</h3>
                  <p>
                    {summary.completedUnits}/{summary.totalUnits} units completed
                  </p>
                  <p className="muted">
                    Active {summary.activeUnits} • Failed {summary.failedUnits}
                  </p>
                  <dl className="mini-stats">
                    <div>
                      <dt>Discovered</dt>
                      <dd>{summary.discoveredCount}</dd>
                    </div>
                    <div>
                      <dt>Accepted</dt>
                      <dd>{summary.acceptedCount}</dd>
                    </div>
                    <div>
                      <dt>Rejected/Merged</dt>
                      <dd>{summary.rejectedCount}</dd>
                    </div>
                  </dl>
                </div>
              ))}
            </div>
          )}
        </article>
      </section>

      <section className="card">
        <h2>Run History</h2>
        {runs.length === 0 ? (
          <p>No runs yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Mode</th>
                  <th>Status</th>
                  <th>Parents</th>
                  <th>Discovered</th>
                  <th>Deduped</th>
                  <th>Inspect</th>
                  <th>CSV</th>
                </tr>
              </thead>
              <tbody>
                {runs.map((run) => (
                  <tr key={run.run_id}>
                    <td>{run.run_name}</td>
                    <td>{run.run_mode}</td>
                    <td>{run.status}</td>
                    <td>{run.parent_entity_count}</td>
                    <td>{run.discovered_club_count}</td>
                    <td>{run.deduped_count}</td>
                    <td>
                      <button className="secondary" onClick={() => loadDiagnostics(run.run_id)}>
                        Inspect
                      </button>
                    </td>
                    <td>
                      <a href={exportCsvUrl(run.run_id)} target="_blank" rel="noreferrer">
                        Download
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>Diagnostics</h2>
        {diagnosticsLoading ? <p>Loading diagnostics...</p> : null}
        {!diagnosticsLoading && !diagnostics ? (
          <p>Select a run to inspect logs, review metadata, and scraped records.</p>
        ) : null}
        {diagnostics ? (
          <>
            <p className="subtitle">
              Run {selectedRunId}: {diagnostics.summary.record_count} records,{" "}
              {diagnostics.summary.review_count} flagged for review, average confidence{" "}
              {diagnostics.summary.average_confidence}, rejected {diagnostics.summary.rejected_count}.
            </p>
            <div className="grid">
              <div>
                <h3>Recent Logs</h3>
                <ul className="stack">
                  {diagnostics.logs.slice(-8).map((log) => (
                    <li key={`${log.shot}-${log.unit_key}-${log.started_at}`}>
                      <strong>{log.shot}</strong> {log.unit_key} [{log.status}]
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3>Review Queue</h3>
                <ul className="stack">
                  {diagnostics.records
                    .filter((record) => record.review_flags.length > 0)
                    .slice(0, 8)
                    .map((record) => (
                      <li key={`${record.parent_key}-${record.business_name}`}>
                        <strong>{record.business_name}</strong> ({record.confidence_score})
                        <br />
                        {record.review_flags.join(", ")}
                      </li>
                    ))}
                </ul>
              </div>
            </div>
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>Scraped Clubs</h2>
        {!diagnostics ? (
          <p>Select a run to view detailed club records.</p>
        ) : diagnostics.records.length === 0 ? (
          <p>No records for this run.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Club</th>
                  <th>Parent</th>
                  <th>Seed</th>
                  <th>Location</th>
                  <th>Confidence</th>
                  <th>Evidence</th>
                  <th>Review</th>
                  <th>Website</th>
                </tr>
              </thead>
              <tbody>
                {diagnostics.records.map((record) => (
                  <tr key={`${record.parent_key}-${record.business_name}-${record.name}`}>
                    <td>
                      <strong>{record.business_name}</strong>
                      <div className="muted">{record.category}</div>
                    </td>
                    <td>
                      <code>{record.parent_key}</code>
                    </td>
                    <td>
                      <code>{record.expansion_seed_id || "n/a"}</code>
                    </td>
                    <td>{record.location || [record.city, record.state].filter(Boolean).join(", ") || "Unknown"}</td>
                    <td>{record.confidence_score}</td>
                    <td>
                      {record.evidence_count} source{record.evidence_count === 1 ? "" : "s"}
                    </td>
                    <td>
                      {record.review_flags.length > 0 ? record.review_flags.join(", ") : "Clear"}
                    </td>
                    <td>
                      {record.website ? (
                        <a href={record.website} target="_blank" rel="noreferrer">
                          Open
                        </a>
                      ) : (
                        <span className="muted">None</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </main>
  );
}
