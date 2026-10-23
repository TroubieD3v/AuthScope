import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const base =
  "w-full rounded-md border border-line bg-bg/70 px-3 text-sm text-ink placeholder:text-mute/70 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent/50 disabled:opacity-50";

export const Input = ({ className, ...p }: InputHTMLAttributes<HTMLInputElement>) => (
  <input className={cn(base, "h-9", className)} {...p} />
);
export const Select = ({ className, ...p }: SelectHTMLAttributes<HTMLSelectElement>) => (
  <select className={cn(base, "h-9 cursor-pointer", className)} {...p} />
);
export const Textarea = ({ className, ...p }: TextareaHTMLAttributes<HTMLTextAreaElement>) => (
  <textarea className={cn(base, "py-2 font-mono text-xs", className)} {...p} />
);

export function Field({ label, hint, children, className }: { label: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <label className={cn("block", className)}>
      <span className="mb-1 block text-xs font-medium text-mute">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-[11px] text-mute/80">{hint}</span>}
    </label>
  );
}

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: ReactNode }) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-sm">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="size-4 accent-[#2dd4bf]" />
      {label}
    </label>
  );
}
