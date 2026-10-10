import { describe, expect, it } from "vitest";
import { artifacts, changes, findings, graph } from "./api/fixtures";
import { buildImpactPath, formatChangeValues } from "./change-evidence";

describe("source evidence details", () => {
  it("shows the protocol change and its path to the visit schedule", () => {
    expect(formatChangeValues(changes[0], graph.facts)).toEqual({
      before: "24 weeks",
      after: "36 weeks",
    });
    const path = buildImpactPath(findings[1], graph);
    expect(path.map(({ from, to, edge }) => ({
      from: `${from.label} · ${artifacts.find((item) => item.id === from.artifact_id)?.name}`,
      to: `${to.label} · ${artifacts.find((item) => item.id === to.artifact_id)?.name}`,
      relationship: edge.relationship,
    }))).toEqual([{
      from: "Primary endpoint · Study protocol",
      to: "Primary endpoint visit · Schedule of assessments",
      relationship: "requires",
    }]);
  });

  it("labels added and removed facts when snapshot IDs are nullable", () => {
    expect(formatChangeValues({
      ...changes[0], kind: "added", before_fact_id: null, before_value: null,
    }, graph.facts)).toMatchObject({ before: "Not present", after: "36 weeks" });
    expect(formatChangeValues({
      ...changes[0], kind: "removed", after_fact_id: null, after_value: null,
    }, graph.facts)).toMatchObject({ before: "24 weeks", after: "Removed" });
  });
});
