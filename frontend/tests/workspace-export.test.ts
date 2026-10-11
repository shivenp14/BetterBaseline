import assert from "node:assert/strict";
import { buildWorkspaceExport, downloadWorkspaceExport, hasCurrentExportableResults } from "../lib/workspace-export";
import { initializeWorkspaceState, workspaceReducer } from "../lib/workspace-state";

async function main() {
  let state = initializeWorkspaceState("baseline-collapse-v1");
  state = workspaceReducer(state, {
    type: "UPDATE_PLANNED_FIELD",
    fieldPointer: "/planned_design/control_event_rate",
    update: { control_event_rate: 0.22 },
  });
  const revision = state.requestRevision + 1;
  state = workspaceReducer(state, {
    type: "START_CALCULATE", requestRevision: revision,
    expectedInputGeneration: state.inputGeneration,
  });
  state = workspaceReducer(state, {
    type: "CALCULATE_SUCCESS",
    response: {
      ...initializeWorkspaceState("baseline-collapse-v1").calculatedDesign!,
      inputs_hash: "sha256:manual-edit-current",
      mock: false,
      execution: { mode: "backend", label: "Calculated by the local backend service" },
    },
    requestRevision: revision,
  });

  const payload = buildWorkspaceExport(state, "2026-10-11T16:00:00.000Z");
  assert.equal(hasCurrentExportableResults(state), true);
  assert.equal(payload.design_result?.inputs_hash, "sha256:manual-edit-current");
  assert.match(payload.inputs_hash, /^sha256:[0-9a-f]{64}$/);
  assert.equal(payload.provenance["/planned_design/control_event_rate"].source, "manual_user");
  assert.equal(payload.evaluation_result, undefined);
  assert.equal(payload.grid_result, undefined);

  let downloadedBlob: Blob | undefined;
  let clicked = false;
  const anchor = {
    href: "",
    download: "",
    click: () => { clicked = true; },
  };
  const oldDocument = Object.getOwnPropertyDescriptor(globalThis, "document");
  const oldCreateObjectURL = URL.createObjectURL;
  const oldRevokeObjectURL = URL.revokeObjectURL;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: { createElement: () => anchor },
  });
  URL.createObjectURL = (blob: Blob) => {
    downloadedBlob = blob;
    return "blob:test-export";
  };
  URL.revokeObjectURL = () => undefined;
  try {
    downloadWorkspaceExport(payload);
  } finally {
    URL.createObjectURL = oldCreateObjectURL;
    URL.revokeObjectURL = oldRevokeObjectURL;
    if (oldDocument) Object.defineProperty(globalThis, "document", oldDocument);
    else delete (globalThis as { document?: unknown }).document;
  }
  assert.equal(clicked, true, "download path clicks a real anchor");
  assert.equal(anchor.download.endsWith(".json"), true);
  const actualDownload = JSON.parse(await downloadedBlob!.text());
  assert.equal(actualDownload.provenance["/planned_design/control_event_rate"].source, "manual_user");
  assert.equal(actualDownload.design_result.inputs_hash, "sha256:manual-edit-current");
  assert.equal(actualDownload.inputs_hash, payload.inputs_hash, "downloaded JSON includes the canonical export-level hash");
  assert.equal(actualDownload.evaluation_result, undefined, "non-current results are omitted");
  console.log("Workspace export regression checks passed (canonical shape/hash, current results and downloaded manual provenance).");
}

void main();
