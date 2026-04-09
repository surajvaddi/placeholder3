"use client";

import { useEffect, useState } from "react";
import { createRun, exportCsvUrl, getRunDiagnostics, listRuns, Run, RunDiagnostics } from "../lib/api";

export default function HomePage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runName, setRunName] = useState("initial-two-shot");
  const [notes, setNotes] = useState("");
  const [mode, setMode] = useState<Run["run_mode"]>("seed_targeted");
  const [seedIds, setSeedIds] = useState("parent_sacnas,expand_sacnas_chapter_directory");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [diagnostics, setDiagnostics] = useState<RunDiagnostics | null>(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);

  async function refreshRuns() {
    try {
      setRuns(await listRuns());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    }
  }

  useEffect(() => {
    refreshRuns();
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
      const parsedSeedIds = seedIds
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean);
      const run = await createRun(runName, notes, mode, parsedSeedIds);
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
        Run a two-shot discovery process and export deduped customer records.
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

      <section className="card">
        <h2>Run History</h2>
        {runs.length === 0 ? (
          <p>No runs yet.</p>
        ) : (
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
                    <a href={exportCsvUrl(run.run_id)} target="_blank">
                      Download
                    </a>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h2>Diagnostics</h2>
        {diagnosticsLoading ? <p>Loading diagnostics...</p> : null}
        {!diagnosticsLoading && !diagnostics ? (
          <p>Select a run to inspect logs and review metadata.</p>
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
    </main>
  );
}
