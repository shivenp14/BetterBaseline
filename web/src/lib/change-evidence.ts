import type { Change, Fact, Finding, Graph } from "@/lib/api/types";

export function formatChangeValues(change: Change, facts: Fact[]) {
  const factById = new Map(facts.map((fact) => [fact.id, fact]));
  const unit =
    (change.after_fact_id && factById.get(change.after_fact_id)?.unit) ??
    (change.before_fact_id && factById.get(change.before_fact_id)?.unit) ??
    null;
  const format = (value: Change["before_value"]) =>
    `${value === null ? "Unknown" : String(value)}${unit ? ` ${unit}` : ""}`;
  return {
    before: change.before_fact_id ? format(change.before_value) : "Not present",
    after: change.after_fact_id ? format(change.after_value) : "Removed",
  };
}

export function buildImpactPath(finding: Finding, graph: Graph) {
  const facts = new Map(graph.facts.map((fact) => [fact.id, fact]));
  const dependencies = new Map(graph.dependencies.map((edge) => [edge.id, edge]));
  return finding.path_edge_ids.flatMap((edgeId) => {
    const edge = dependencies.get(edgeId);
    const from = edge && facts.get(edge.from_fact_id);
    const to = edge && facts.get(edge.to_fact_id);
    return edge && from && to
      ? [{ edge, from, to }]
      : [];
  });
}
