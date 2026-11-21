import { Check } from "lucide-react";
import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const base =
  "w-full border border-line bg-bg px-2.5 text-[12.5px] text-ink placeholder:text-dim transition-colors focus:border-accent focus:outline-none disabled:opacity-50";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={cn(base, "h-8", className)} {...p} />
);
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn(base, "h-8 cursor-pointer", className)} {...p} />
);
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cn(base, "py-1.5 font-mono text-xs", className)} {...p} />
);

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1 block text-xs text-mute">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-dim">{hint}</span>}
    </label>
  );
}

/** Checkbox-style switch, as in a scan configuration list. */
export function Switch({ checked, onChange, label, tone = "accent", disabled }: {
  checked: boolean; onChange: (v: boolean) => void; label?: string; tone?: "accent" | "warn"; disabled?: boolean;
}) {
  return (
    <button
      type="button" role="switch" aria-checked={checked} aria-label={label} disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "grid size-4 shrink-0 cursor-pointer place-items-center border transition-colors disabled:cursor-not-allowed disabled:opacity-40",
        checked ? (tone === "warn" ? "border-warn-solid bg-warn-solid" : "border-accent-solid bg-accent-solid") : "border-dim bg-bg hover:border-mute",
      )}
    >
      {checked && <Check className="size-3 text-white" strokeWidth={3} />}
    </button>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-[12.5px]">
      <Switch checked={checked} onChange={onChange} />
      <span>{label}</span>
    </label>
  );
}
