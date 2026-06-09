"use client";
import { tokens } from "../../config/theme/tokens";

export interface SegmentedOption<T extends string = string> {
  value: T;
  label: string;
}

interface SegmentedControlProps<T extends string = string> {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

export function SegmentedControl<T extends string = string>({ options, value, onChange }: SegmentedControlProps<T>) {
  return (
    <div style={{
      display: "flex",
      gap: tokens.space[1],
      background: tokens.color.surface,
      borderRadius: tokens.radius.md,
      padding: 3,
      marginBottom: tokens.space[4],
      flexWrap: "wrap",
    }}>
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onChange(opt.value)}
          style={{
            padding: `6px 12px`,
            borderRadius: tokens.radius.md,
            border: "none",
            cursor: "pointer",
            fontSize: tokens.font.sizeSm,
            fontWeight: 600,
            background: value === opt.value ? tokens.color.accent : "transparent",
            color: value === opt.value ? "#fff" : tokens.color.textMuted,
            transition: `background ${tokens.transition.fast}`,
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
