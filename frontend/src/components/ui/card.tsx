import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

/** A docked panel: hairline border, flat surface. */
export function Card({ className, tone = "surface", ...props }: HTMLAttributes<HTMLDivElement> & { tone?: "surface" | "container" | "inverse" }) {
  void tone;
  return <div className={cn("relative min-w-0 border border-line bg-panel", className)} {...props} />;
}

/** Panel title bar, like the header strip of a tool window. */
export function CardHeader({ title, hint, actions }: { title: ReactNode; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-b border-line bg-panel2/60 px-3 py-1.5">
      <div className="min-w-0">
        <h3 className="text-[12.5px] font-semibold">{title}</h3>
        {hint && <p className="text-xs text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex items-center gap-1.5">{actions}</div>}
    </div>
  );
}

export const CardBody = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-3 py-3", className)} {...props} />
);

/** Counter cell: small label, tabular number. */
export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: "bad" | "warn" | "ok"; hint?: ReactNode }) {
  const color = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <div className="bg-panel px-3 py-2">
      <div className="text-xs text-mute">{label}</div>
      <div className={cn("mt-0.5 font-mono text-xl font-medium", color)}>{value}</div>
      {hint && <div className="text-xs text-mute">{hint}</div>}
    </div>
  );
}

/** Thin progress bar. */
export function Bar({ value, tone = "accent", className }: { value: number; tone?: "accent" | "ink" | "warn" | "bad"; className?: string }) {
  const fill = { accent: "bg-ok", ink: "bg-dim", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <div className={cn("h-1.5 w-full overflow-hidden bg-high", className)}>
      <div className={cn("h-full transition-all duration-500", fill)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

/** Plain icon slot; colour only when it reports a state. */
export function IconTile({ children, tone = "accent", className }: { children: ReactNode; tone?: "accent" | "ink" | "warn" | "bad" | "info"; className?: string }) {
  const tones = { accent: "text-mute", ink: "text-ink", warn: "text-warn", bad: "text-bad", info: "text-info" };
  return <div className={cn("grid size-7 shrink-0 place-items-center", tones[tone], className)}>{children}</div>;
}
