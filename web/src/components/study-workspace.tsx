"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { createStudyApi, parseApiMode } from "@/lib/api/client";
import type { Artifact, Finding, Study } from "@/lib/api/types";
interface WorkspaceData {
  studies: Study[];
  study: Study | null;
  artifacts: Artifact[];
  findings: Finding[];
}
export function StudyWorkspace() {
  const [data, setData] = useState<WorkspaceData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [selectedId, setSelectedId] = useState("");
  const [loading, setLoading] = useState(true);
  const modeLabel = process.env.NEXT_PUBLIC_API_MODE || "fixture";
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        const api = createStudyApi({
          mode: parseApiMode(process.env.NEXT_PUBLIC_API_MODE),
          baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
        });
        const { items: studies } = await api.listStudies();
        const study =
          studies.find((item) => item.id === selectedId) ?? studies[0] ?? null;
        const [artifacts, findings] = study
          ? await Promise.all([
              api.listArtifacts(study.id),
              api.listFindings(study.id),
            ])
          : [{ items: [] }, { items: [] }];
        if (active) {
          setData({
            studies,
            study,
            artifacts: artifacts.items,
            findings: findings.items,
          });
          setLoading(false);
        }
      } catch (error) {
        if (active) {
          setError(
            error instanceof Error
              ? error.message
              : "Unable to load the workspace.",
          );
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [attempt, selectedId]);
  const openCount =
    data?.findings.filter(
      (finding) => finding.status === "open" || finding.status === "in_review",
    ).length ?? 0;
  const retry = () => {
    setError(null);
    setLoading(true);
    setAttempt((value) => value + 1);
  };
  return (
    <div className="shell">
      <header className="topbar">
        <Link className="brand" href="/" aria-label="TrialSync home">
          <span className="brand-mark" aria-hidden="true">
            T
          </span>
          TrialSync
        </Link>
        <span className="workspace-label">STUDY WORKSPACE</span>
        <span className="mode">
          {modeLabel === "fixture"
            ? "Fixture mode · Synthetic data"
            : modeLabel === "live"
              ? "Live API"
              : "Invalid API mode"}
        </span>
      </header>
      <main>
        <div className="intro">
          <div>
            <p className="eyebrow">WORKSPACE / OVERVIEW</p>
            <h1>Your study, in view.</h1>
            <p className="subtitle">
              Keep study documents and change findings together.
            </p>
          </div>
          {data && data.studies.length > 0 && (
            <div className="study-selector">
              <label htmlFor="study">Current study</label>
              <select
                id="study"
                value={data.study?.id ?? ""}
                disabled={loading}
                onChange={(event) => {
                  setError(null);
                  setLoading(true);
                  setSelectedId(event.target.value);
                }}
              >
                {data.studies.map((study) => (
                  <option key={study.id} value={study.id}>
                    {study.name}
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
        {loading ? (
          <section className="state" role="status">
            Loading study workspace…
          </section>
        ) : error ? (
          <section className="state" role="alert">
            <h2>Workspace unavailable</h2>
            <p>{error}</p>
            <button onClick={retry}>Try again</button>
          </section>
        ) : !data?.study ? (
          <section className="state">
            <h2>No studies yet</h2>
            <p>
              The API returned no studies. Add a study in the backend to begin.
            </p>
          </section>
        ) : (
          <>
            <section className="study-banner" aria-labelledby="study-title">
              <div>
                <p className="eyebrow">
                  {modeLabel === "fixture" ? "SYNTHETIC DEMO" : "CURRENT STUDY"}
                </p>
                <h2 id="study-title">{data.study.name}</h2>
                <p>
                  {data.study.description || "Study artifacts and findings."}
                </p>
              </div>
              <span className="study-tag">Study overview</span>
            </section>
            <section className="metrics" aria-label="Study counts">
              <div>
                <span>Artifacts</span>
                <strong>{data.artifacts.length}</strong>
                <p>Study documents in this workspace</p>
              </div>
              <div>
                <span>Findings</span>
                <strong>{data.findings.length}</strong>
                <p>Change findings across the study</p>
              </div>
              <div>
                <span>Needs attention</span>
                <strong>{openCount}</strong>
                <p>Open or in-review findings</p>
              </div>
            </section>
            <div className="panels">
              <section className="panel" aria-labelledby="artifacts-title">
                <div className="panel-heading">
                  <h2 id="artifacts-title">Study artifacts</h2>
                  <span>{data.artifacts.length} documents</span>
                </div>
                {data.artifacts.length === 0 ? (
                  <p className="empty">No artifacts in this study.</p>
                ) : (
                  <ul className="artifact-list">
                    {data.artifacts.map((artifact) => {
                      const latest = artifact.versions?.reduce<
                        Artifact["versions"][number] | undefined
                      >(
                        (current, version) =>
                          !current ||
                          version.version_number > current.version_number
                            ? version
                            : current,
                        undefined,
                      );
                      return (
                        <li key={artifact.id}>
                          <span className="document-icon" aria-hidden="true">
                            ▤
                          </span>
                          <div>
                            <h3>{artifact.name}</h3>
                            <p>
                              {artifact.kind}
                              {latest
                                ? ` · Version ${latest.version_number}`
                                : ""}
                            </p>
                          </div>
                          {latest && (
                            <span className={`status ${latest.status}`}>
                              {latest.status}
                            </span>
                          )}
                        </li>
                      );
                    })}
                  </ul>
                )}
              </section>
              <section className="panel" aria-labelledby="findings-title">
                <div className="panel-heading">
                  <h2 id="findings-title">Change findings</h2>
                  <span>{openCount} need attention</span>
                </div>
                {data.findings.length === 0 ? (
                  <p className="empty">No change findings in this study.</p>
                ) : (
                  <ul className="finding-list">
                    {data.findings.map((finding) => (
                      <li key={finding.id}>
                        <div className="finding-top">
                          <h3>
                            {data.artifacts.find(
                              (artifact) =>
                                artifact.id === finding.affected_artifact_id,
                            )?.name ?? "Affected artifact"}
                          </h3>
                          <span className="status finding-status">
                            {finding.status.replaceAll("_", " ")}
                          </span>
                        </div>
                        <p>{finding.explanation}</p>
                        <span className="finding-action">
                          {finding.action.replaceAll("_", " ")}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
            {modeLabel === "fixture" && (
              <p className="demo-note">
                Demo context: protocol v2 moves the endpoint from week 24 to
                week 36. Two documents need review; the historical report
                remains pinned to its original context.
              </p>
            )}
          </>
        )}
      </main>
      <footer>
        TrialSync<span>Trace changes. Keep context.</span>
      </footer>
    </div>
  );
}
