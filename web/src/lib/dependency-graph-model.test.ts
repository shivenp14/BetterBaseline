import { describe, expect, it } from "vitest";
import { artifacts, changes, findings, graph } from "./api/fixtures";
import { projectDependencyGraph } from "./dependency-graph-model";

describe("dependency graph projection", () => {
  it.each(["added", "removed"] as const)("highlights %s facts with a nullable snapshot ID", (kind) => {
    const factId = graph.facts[0].id;
    const change = {
      ...changes[0],
      kind,
      before_fact_id: kind === "added" ? null : factId,
      after_fact_id: kind === "removed" ? null : factId,
    };
    const { nodes } = projectDependencyGraph({
      graph,
      artifacts,
      changes: [change],
      findings: [],
    });
    expect(nodes.find((node) => node.id === factId)?.data.changed).toBe(true);
  });

  it("points upstream facts to dependents and exposes confirmed/current and proposed/current styles", () => {
    const { nodes, edges } = projectDependencyGraph({
      graph,
      artifacts,
      changes,
      findings,
    });
    expect(edges.map(({ source, target, label }) => ({ source, target, label }))).toEqual([
      {
        source: "00000000-0000-4000-8000-000000000201",
        target: "00000000-0000-4000-8000-000000000202",
        label: "confirmed · current",
      },
      {
        source: "00000000-0000-4000-8000-000000000201",
        target: "00000000-0000-4000-8000-000000000203",
        label: "proposed · current",
      },
      {
        source: "00000000-0000-4000-8000-000000000205",
        target: "00000000-0000-4000-8000-000000000204",
        label: "confirmed · pinned",
      },
    ]);
    expect(edges[0].style?.strokeDasharray).toBeUndefined();
    expect(edges[1].style?.strokeDasharray).toBe("3 4");
    expect(edges[2].style?.strokeDasharray).toBe("6 5");
    expect(nodes.find((node) => node.id.endsWith("201"))?.position.x).toBeLessThan(
      nodes.find((node) => node.id.endsWith("202"))!.position.x,
    );
  });

  it("highlights changed and finding-affected facts without marking pinned historical context", () => {
    const { nodes } = projectDependencyGraph({
      graph,
      artifacts,
      changes,
      findings,
    });
    expect(nodes.find((node) => node.id.endsWith("201"))?.data).toMatchObject({
      changed: true,
      affected: false,
    });
    expect(nodes.find((node) => node.id.endsWith("202"))?.data.affected).toBe(true);
    expect(nodes.find((node) => node.id.endsWith("203"))?.data.affected).toBe(true);
    expect(nodes.find((node) => node.id.endsWith("204"))?.data).toMatchObject({
      changed: false,
      affected: false,
      pinned: true,
    });
    expect(nodes.find((node) => node.id.endsWith("205"))?.data).toMatchObject({
      changed: false,
      affected: false,
      pinned: true,
    });
  });
});
