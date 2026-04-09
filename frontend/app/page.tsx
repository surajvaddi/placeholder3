"use client";

import { useEffect, useState } from "react";
import { createRun, exportCsvUrl, listRuns, Run } from "../lib/api";

export default function HomePage() {
  const [runs, setRuns] = useState<Run[]>([]);
  const [runName, setRunName] = useState("initial-two-shot");
  const [notes, setNotes] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

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

  async function onCreateRun() {
    setLoading(true);
    setError("");
    try {
      await createRun(runName, notes);
      await refreshRuns();
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
                <th>Status</th>
                <th>Parents</th>
                <th>Discovered</th>
                <th>Deduped</th>
                <th>CSV</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr key={run.run_id}>
                  <td>{run.run_name}</td>
                  <td>{run.status}</td>
                  <td>{run.parent_entity_count}</td>
                  <td>{run.discovered_club_count}</td>
                  <td>{run.deduped_count}</td>
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
    </main>
  );
}
