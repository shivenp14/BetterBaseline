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
    <section aria-labelledby="preset-heading">
      <h2 id="preset-heading">Synthetic Presets & Scenario Selection</h2>
      <p>
        Select a versioned synthetic preset or reset the current scenario to initial defaults.
        Editing assumptions will update field provenance to <code>manual_user</code>.
      </p>

      <div>
        <label htmlFor="preset-select">
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
        </select>
        {onResetPreset && (
          <button type="button" onClick={onResetPreset} style={{ marginLeft: "8px" }}>
            Reset to Preset Defaults
          </button>
        )}
      </div>

      <div style={{ marginTop: "8px" }}>
        <p>
          <em>{currentPreset.description}</em>
        </p>
        <p>
          <strong>Inputs Hash:</strong> <code>{currentPreset.inputs_hash}</code>
        </p>
      </div>
    </section>
  );
}
