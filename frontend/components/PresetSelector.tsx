"use client";

import React from "react";
import { rawPresets } from "@/lib/presets";

interface PresetSelectorProps {
  selectedPresetId: string;
  onSelectPreset: (presetId: string) => void;
  onResetPreset?: () => void;
}

export function PresetSelector({
  selectedPresetId,
  onSelectPreset,
  onResetPreset,
}: PresetSelectorProps) {
  const currentPreset = rawPresets.find((p) => p.preset_id === selectedPresetId) ?? rawPresets[0];

  return (
    <section className="panel preset-panel" aria-labelledby="preset-heading">
      <h2 className="section-heading" id="preset-heading">Synthetic Presets & Scenario Selection</h2>
      <p className="muted">
        Select a versioned synthetic preset or reset the current scenario to initial defaults.
        Editing assumptions will update field provenance to <code className="inline-code">manual_user</code>.
      </p>

      <div className="preset-actions action-row">
        <div className="field"><label htmlFor="preset-select">
          <strong>Select Preset:</strong>{" "}
        </label>
        <select
          id="preset-select"
          value={selectedPresetId}
          onChange={(e) => onSelectPreset(e.target.value)}
        >
          {rawPresets.map((preset) => (
            <option key={preset.preset_id} value={preset.preset_id}>
              {preset.name} ({preset.eyebrow})
            </option>
          ))}
        </select></div>
        {onResetPreset && (
          <button type="button" onClick={onResetPreset} className="button-secondary">
            Reset to Preset Defaults
          </button>
        )}
      </div>

      <div className="preset-description">
        <p>
          <em>{currentPreset.description}</em>
        </p>
        <details className="disclosure"><summary>Preset identity and provenance</summary>
        <p className="field-help">Edits are recorded as <code className="inline-code">manual_user</code>.</p>
        <p>
          <strong>Inputs Hash:</strong> <code className="inline-code">{currentPreset.inputs_hash}</code>
        </p></details>
      </div>
    </section>
  );
}
