"use client";

import {
  Background,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useEffect, useMemo, useState } from "react";
import type { Artifact, Change, Fact, Finding, Graph, Source } from "@/lib/api/types";
import { createStudyApi, parseApiMode } from "@/lib/api/client";
import { buildImpactPath, formatChangeValues } from "@/lib/change-evidence";
import {
  projectDependencyGraph,
  type FactNode,
} from "@/lib/dependency-graph-model";

function FactCard({ data }: NodeProps<FactNode>) {
  return (
    <article
      className={`fact-card${data.changed ? " is-changed" : ""}${data.affected ? " is-affected" : ""}${data.pinned ? " is-pinned" : ""}`}
    >
      <Handle type="target" position={Position.Left} aria-label="Upstream dependency" />
      <div className="fact-card-top">
        <span className="fact-artifact">{data.artifactKind}</span>
        {data.versionNumber !== null && <span>v{data.versionNumber}</span>}
      </div>
      <h3>{data.label}</h3>
      <p className="fact-value">{data.value}</p>
      <p className="fact-document">{data.artifactName}</p>
      <p className="fact-source">{data.source}</p>
      {(data.changed || data.affected || data.pinned) && (
        <div className="fact-badges">
          {data.changed && <span className="fact-badge changed-badge">Changed</span>}
          {data.affected && <span className="fact-badge affected-badge">Finding · affected</span>}
          {data.pinned && <span className="fact-badge pinned-badge">Pinned historical</span>}
        </div>
      )}
      <Handle type="source" position={Position.Right} aria-label="Downstream dependency" />
    </article>
  );
}

const nodeTypes = { fact: FactCard };

type Selection = { type: "node"; id: string } | { type: "edge"; id: string };

function valueText(value: Fact["value"], unit: string | null) {
  return `${value === null ? "Unknown" : String(value)}${unit ? ` ${unit}` : ""}`;
}

function uniqueSources(sources: Source[]) {
  return [...new Map(sources.map((source) => [source.fragment_id, source])).values()];
}

export function DependencyGraph({
  graph,
  artifacts,
  changes,
  findings,
}: {
  graph: Graph | null;
  artifacts: Artifact[];
  changes: Change[];
  findings: Finding[];
}) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const [sourceUrl, setSourceUrl] = useState<string | null>(null);
  const [sourceState, setSourceState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const projected = useMemo(
    () =>
      graph
        ? projectDependencyGraph({ graph, artifacts, changes, findings })
        : null,
    [graph, artifacts, changes, findings],
  );

  const factById = useMemo(
    () => new Map((graph?.facts ?? []).map((fact) => [fact.id, fact])),
    [graph],
  );
  const dependencyById = useMemo(
    () => new Map((graph?.dependencies ?? []).map((edge) => [edge.id, edge])),
    [graph],
  );
  const selectedFact = selection?.type === "node" ? factById.get(selection.id) : undefined;
  const selectedDependency = selection?.type === "edge" ? dependencyById.get(selection.id) : undefined;
  const relatedFindings = findings.filter((finding) =>
    selectedFact
      ? finding.affected_fact_id === selectedFact.id ||
        changes.some((change) => change.id === finding.change_id &&
          (change.before_fact_id === selectedFact.id || change.after_fact_id === selectedFact.id))
      : selectedDependency
        ? finding.path_edge_ids.includes(selectedDependency.id)
        : false,
  );
  const relatedChanges = changes.filter((change) =>
    selectedFact
      ? change.before_fact_id === selectedFact.id ||
        change.after_fact_id === selectedFact.id ||
        relatedFindings.some((finding) => finding.change_id === change.id)
      : selectedDependency
        ? change.after_fact_id === selectedDependency.from_fact_id ||
          relatedFindings.some((finding) => finding.change_id === change.id)
        : false,
  );
  const primaryChange = relatedChanges[0];
  const evidenceSources = uniqueSources([
    ...(selectedFact ? [selectedFact.source] : []),
    ...(selectedDependency?.evidence ?? []),
    ...relatedFindings.flatMap((finding) => finding.sources),
    ...(primaryChange
      ? [primaryChange.before_fact_id, primaryChange.after_fact_id]
          .flatMap((id) => (id ? factById.get(id)?.source ?? [] : []))
      : []),
  ]);
  const linkFact = selectedFact ?? (selectedDependency ? factById.get(selectedDependency.from_fact_id) : undefined);
  const visibleNodes = projected?.nodes.map((node) => ({
    ...node,
    selected: selection?.type === "node" && selection.id === node.id,
  }));
  const visibleEdges = projected?.edges.map((edge) => ({
    ...edge,
    selected: selection?.type === "edge" && selection.id === edge.id,
  }));

  useEffect(() => {
    let active = true;
    if (!selection || !linkFact) {
      return () => { active = false; };
    }
    let sourceRequest: Promise<string | null>;
    try {
      const api = createStudyApi({
        mode: parseApiMode(process.env.NEXT_PUBLIC_API_MODE),
        baseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
      });
      sourceRequest = api.getOriginalFileUrl(linkFact.artifact_id, linkFact.version_id);
    } catch {
      void Promise.resolve().then(() => {
        if (active) setSourceState("error");
      });
      return () => { active = false; };
    }
    void Promise.resolve()
      .then(() => {
        if (active) {
          setSourceUrl(null);
          setSourceState("loading");
        }
        return sourceRequest;
      })
      .then((url) => {
        if (!active) return;
        setSourceUrl(url);
        setSourceState("ready");
      })
      .catch(() => {
        if (active) setSourceState("error");
      });
    return () => { active = false; };
  }, [selection, linkFact]);

  return (
    <section className="graph-panel" aria-labelledby="dependency-graph-title">
      <div className="graph-heading">
        <div>
          <p className="eyebrow">DEPENDENCY MAP</p>
          <h2 id="dependency-graph-title">How study facts connect</h2>
          <p>Arrows point from an upstream fact to the facts that depend on it.</p>
        </div>
        <div className="graph-legend" aria-label="Graph legend">
          <span><i className="legend-line confirmed-line" />Confirmed</span>
          <span><i className="legend-line proposed-line" />Proposed</span>
          <span><i className="legend-line pinned-line" />Pinned · excluded from propagation</span>
          <span><i className="legend-dot changed-dot" />Changed</span>
          <span><i className="legend-dot affected-dot" />Finding affected</span>
        </div>
      </div>
      {!projected ? (
        <p className="graph-empty">
          Dependency data is not available from the current workspace API.
        </p>
      ) : projected.nodes.length === 0 ? (
        <p className="graph-empty">No facts or dependencies are available for this study.</p>
      ) : (
        <div className="graph-canvas" aria-label="Study fact dependency graph">
          <ReactFlow
            nodes={visibleNodes ?? []}
            edges={visibleEdges ?? []}
            nodeTypes={nodeTypes}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable
            panOnDrag={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            onNodeClick={(_, node) => setSelection({ type: "node", id: node.id })}
            onEdgeClick={(_, edge) => setSelection({ type: "edge", id: edge.id })}
            onPaneClick={() => setSelection(null)}
            fitView
            fitViewOptions={{ padding: 0.18, minZoom: 0.35, maxZoom: 1 }}
          >
            <Background color="#e8eeeb" gap={22} size={1} />
          </ReactFlow>
        </div>
      )}
      {projected && (
        <aside className="evidence-panel" aria-live="polite" aria-labelledby="evidence-title">
          <div className="evidence-heading">
            <div>
              <p className="eyebrow">SOURCE EVIDENCE</p>
              <h3 id="evidence-title">
                {selectedFact?.label ?? (selectedDependency ? "Dependency evidence" : "Inspect a graph item")}
              </h3>
            </div>
            {selection && <button className="evidence-clear" onClick={() => setSelection(null)}>Clear selection</button>}
          </div>
          {!selection ? (
            <p className="evidence-empty">Select a fact or connection to inspect its source, change details, and impact path.</p>
          ) : (
            <div className="evidence-content">
              {selectedFact && (
                <div className="evidence-section">
                  <span className="evidence-label">Selected fact</span>
                  <p>{selectedFact.label}: <strong>{valueText(selectedFact.value, selectedFact.unit)}</strong></p>
                  <p className="evidence-locator">{selectedFact.source.locator}</p>
                </div>
              )}
              {evidenceSources.length > 0 ? (
                <div className="evidence-section">
                  <span className="evidence-label">Source quote{evidenceSources.length > 1 ? "s" : ""}</span>
                  {evidenceSources.map((source) => (
                    <blockquote key={source.fragment_id}>
                      <span>{source.locator}</span>
                      <p>“{source.quote}”</p>
                    </blockquote>
                  ))}
                </div>
              ) : <p className="evidence-empty">No source quote is available for this selection.</p>}
              {primaryChange && (
                <div className="evidence-section">
                  <span className="evidence-label">Change · {primaryChange.kind}</span>
                  <div className="change-values">
                    <div><span>Before</span><strong>{formatChangeValues(primaryChange, graph?.facts ?? []).before}</strong></div>
                    <span aria-hidden="true">→</span>
                    <div><span>After</span><strong>{formatChangeValues(primaryChange, graph?.facts ?? []).after}</strong></div>
                  </div>
                </div>
              )}
              {relatedFindings.length > 0 ? (
                <div className="evidence-section">
                  <span className="evidence-label">Impact path</span>
                  {relatedFindings.map((finding) => (
                    <div className="impact-path" key={finding.id}>
                      {buildImpactPath(finding, graph ?? { facts: [], dependencies: [] }).map(({ edge: dependency, from: fromFact, to: toFact }, index) => {
                        return <span key={dependency.id}>
                          {index === 0 && <strong>{fromFact.label}</strong>}
                          <i aria-hidden="true">→</i>
                          <strong>{toFact.label}</strong>
                          <small>{dependency.relationship.replaceAll("_", " ")} · {dependency.tracking}</small>
                        </span>;
                      })}
                      <p>{finding.explanation}</p>
                    </div>
                  ))}
                </div>
              ) : selectedDependency ? (
                <div className="evidence-section">
                  <span className="evidence-label">Impact path</span>
                  <p>{factById.get(selectedDependency.from_fact_id)?.label} → {factById.get(selectedDependency.to_fact_id)?.label}</p>
                  <p className="evidence-locator">{selectedDependency.relationship.replaceAll("_", " ")} · {selectedDependency.tracking} · {selectedDependency.status}</p>
                </div>
              ) : null}
              <div className="evidence-section original-file">
                <span className="evidence-label">Original file</span>
                {sourceState === "loading" ? <p role="status">Looking for the source file…</p>
                  : sourceState === "error" ? <p role="status">The source file link could not be loaded.</p>
                  : sourceUrl ? <a href={sourceUrl} target="_blank" rel="noreferrer">Open original file</a>
                  : <p>The original file is not available for this evidence.</p>}
              </div>
            </div>
          )}
        </aside>
      )}
    </section>
  );
}
