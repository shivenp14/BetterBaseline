"use client";

import {
  Background,
  Handle,
  Position,
  ReactFlow,
  type NodeProps,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useMemo } from "react";
import type { Artifact, Change, Finding, Graph } from "@/lib/api/types";
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
  const projected = useMemo(
    () =>
      graph
        ? projectDependencyGraph({ graph, artifacts, changes, findings })
        : null,
    [graph, artifacts, changes, findings],
  );

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
            nodes={projected.nodes}
            edges={projected.edges}
            nodeTypes={nodeTypes}
            nodesDraggable={false}
            nodesConnectable={false}
            elementsSelectable={false}
            panOnDrag={false}
            zoomOnScroll={false}
            zoomOnPinch={false}
            zoomOnDoubleClick={false}
            fitView
            fitViewOptions={{ padding: 0.18, minZoom: 0.35, maxZoom: 1 }}
          >
            <Background color="#e8eeeb" gap={22} size={1} />
          </ReactFlow>
        </div>
      )}
    </section>
  );
}
