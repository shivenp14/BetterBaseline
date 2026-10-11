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
    <section className="planning-presets" aria-labelledby="preset-heading">
      <h2 id="preset-heading">Choose a starting example</h2>
      <p>
        Examples use made-up assumptions to show how this workspace works; they are not taken from a real trial. Choose one to replace the current values, or keep the selected example and edit it below.
      </p>

      <div className="planning-presetControls">
        <label htmlFor="preset-select">
          <strong>Starting example:</strong>{" "}
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
          <button type="button" onClick={onResetPreset}>
            Restore example values
          </button>
        )}
      </div>

      <div className="planning-presetDetails">
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
