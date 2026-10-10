import { MarkerType, type Edge, type Node } from "@xyflow/react";
import type {
  Artifact,
  Change,
  Dependency,
  Fact,
  Finding,
  Graph,
} from "@/lib/api/types";

export interface FactNodeData extends Record<string, unknown> {
  artifactName: string;
  artifactKind: string;
  versionNumber: number | null;
  label: string;
  value: string;
  source: string;
  changed: boolean;
  affected: boolean;
  pinned: boolean;
}

export interface DependencyEdgeData extends Record<string, unknown> {
  relationship: Dependency["relationship"];
  tracking: Dependency["tracking"];
  status: Dependency["status"];
}

export type FactNode = Node<FactNodeData, "fact">;
export type DependencyEdge = Edge<DependencyEdgeData>;

export function projectDependencyGraph(input: {
  graph: Graph;
  artifacts: Artifact[];
  changes: Change[];
  findings: Finding[];
}): { nodes: FactNode[]; edges: DependencyEdge[] } {
  const { graph, artifacts, changes, findings } = input;
  const factById = new Map(graph.facts.map((fact) => [fact.id, fact]));
  const artifactById = new Map(artifacts.map((artifact) => [artifact.id, artifact]));
  const versions = new Map(
    artifacts.flatMap((artifact) => artifact.versions.map((version) => [version.id, version] as const)),
  );
  const changedFactIds = new Set(
    changes.flatMap((change) => {
      const currentFactId = change.after_fact_id ?? change.before_fact_id;
      return currentFactId ? [currentFactId] : [];
    }),
  );
  const affectedFactIds = new Set(findings.map((finding) => finding.affected_fact_id));
  const currentSources = new Set(
    graph.dependencies
      .filter((dependency) => dependency.tracking === "current")
      .map((dependency) => dependency.from_fact_id),
  );
  const currentTargets = new Set(
    graph.dependencies
      .filter((dependency) => dependency.tracking === "current")
      .map((dependency) => dependency.to_fact_id),
  );
  const pinnedSources = new Set(
    graph.dependencies
      .filter((dependency) => dependency.tracking === "pinned")
      .map((dependency) => dependency.from_fact_id),
  );
  const pinnedTargets = new Set(
    graph.dependencies
      .filter((dependency) => dependency.tracking === "pinned")
      .map((dependency) => dependency.to_fact_id),
  );
  // The before-fact on a modification can represent preserved historical
  // context. Pinned context remains neutral even when it is the change's
  // before value; the current after-fact carries the changed highlight.
  for (const factId of [...pinnedSources, ...pinnedTargets]) {
    changedFactIds.delete(factId);
  }
  const sourceFacts = graph.facts.filter(
    (fact) => currentSources.has(fact.id) || pinnedSources.has(fact.id),
  );
  const targetFacts = graph.facts.filter(
    (fact) => currentTargets.has(fact.id) || pinnedTargets.has(fact.id),
  );
  const rowByFact = new Map<string, number>();
  const assignRows = (facts: Fact[]) => {
    const byArtifact = new Map<string, Fact[]>();
    for (const fact of facts) {
      const bucket = byArtifact.get(fact.artifact_id) ?? [];
      bucket.push(fact);
      byArtifact.set(fact.artifact_id, bucket);
    }
    let row = 0;
    for (const artifact of artifacts) {
      const group = byArtifact.get(artifact.id) ?? [];
      for (const fact of group) rowByFact.set(fact.id, row++);
    }
    for (const fact of facts) {
      if (!rowByFact.has(fact.id)) rowByFact.set(fact.id, row++);
    }
  };
  assignRows(sourceFacts);
  assignRows(targetFacts);

  const nodes: FactNode[] = graph.facts.map((fact) => {
    const artifact = artifactById.get(fact.artifact_id);
    const version = versions.get(fact.version_id);
    const isSource = currentSources.has(fact.id) || pinnedSources.has(fact.id);
    const isPinned = pinnedSources.has(fact.id) || pinnedTargets.has(fact.id);
    return {
      id: fact.id,
      type: "fact",
      position: {
        x: isSource ? 38 : 520,
        y: 40 + (rowByFact.get(fact.id) ?? 0) * 178,
      },
      data: {
        artifactName: artifact?.name ?? "Unknown artifact",
        artifactKind: artifact?.kind ?? "Artifact",
        versionNumber: version?.version_number ?? null,
        label: fact.label,
        value: `${fact.value}${fact.unit ? ` ${fact.unit}` : ""}`,
        source: fact.source.locator,
        changed: changedFactIds.has(fact.id),
        affected: affectedFactIds.has(fact.id),
        pinned: isPinned,
      },
      draggable: false,
      selectable: true,
    };
  });

  const edges: DependencyEdge[] = graph.dependencies
    .filter((dependency) => factById.has(dependency.from_fact_id) && factById.has(dependency.to_fact_id))
    .map((dependency) => {
      const pinned = dependency.tracking === "pinned";
      const statusColor = dependency.status === "confirmed" ? "#17675b" : "#a77b2b";
      return {
        id: dependency.id,
        source: dependency.from_fact_id,
        target: dependency.to_fact_id,
        type: "smoothstep",
        label: `${dependency.status} · ${dependency.tracking}`,
        labelStyle: { fill: pinned ? "#66706d" : statusColor, fontSize: 11, fontWeight: 600 },
        labelBgStyle: { fill: "#ffffff", fillOpacity: 0.96 },
        labelBgPadding: [6, 4],
        labelBgBorderRadius: 5,
        markerEnd: { type: MarkerType.ArrowClosed, color: pinned ? "#8a9691" : statusColor },
        style: {
          stroke: pinned ? "#8a9691" : statusColor,
          strokeWidth: 2,
          strokeDasharray: pinned ? "6 5" : dependency.status === "proposed" ? "3 4" : undefined,
        },
        data: {
          relationship: dependency.relationship,
          tracking: dependency.tracking,
          status: dependency.status,
        },
        selectable: true,
        deletable: false,
      };
    });

  return { nodes, edges };
}
