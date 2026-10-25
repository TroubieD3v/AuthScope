import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

// Square, tinted inputs like the palette's search field.
const base =
  "w-full rounded-[3px] border border-line bg-panel2/70 px-3 text-sm text-ink placeholder:text-mute/70 transition-colors focus:border-accent focus:bg-panel focus:outline-none focus:ring-2 focus:ring-accent/25 disabled:opacity-50";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={cn(base, "h-10", className)} {...p} />
);
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn(base, "h-10 cursor-pointer", className)} {...p} />
);
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cn(base, "py-2 font-mono text-xs", className)} {...p} />
);

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] text-mute">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-mute/80">{hint}</span>}
    </label>
  );
}

/** Pill switch (green when on). */
export function Switch({ checked, onChange, label, tone = "accent", disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string; tone?: "accent" | "warn"; disabled?: boolean;
}) {
  return (
    <button
      type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative h-7 w-12 shrink-0 cursor-pointer rounded-full transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        checked ? (tone === "warn" ? "bg-warn-solid" : "bg-accent-solid") : "bg-high",
      )}
    >
      <span className={cn("absolute top-1 left-1 size-5 rounded-full bg-white shadow transition-transform", checked && "translate-x-5")} />
    </button>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-3 text-sm">
      <Switch checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}
