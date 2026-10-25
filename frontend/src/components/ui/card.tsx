import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, tone = "surface", ...props }: HTMLAttributes<HTMLDivElement> & { tone?: "surface" | "container" | "inverse" }) {
  const tones = {
    surface: "bg-panel shadow-[0_24px_40px_-16px_rgb(11_28_48/0.10)] dark:shadow-none ring-1 ring-line/60",
    container: "bg-panel2",
    inverse: "bg-inverse text-on-inverse",
  };
  return <div className={cn("relative overflow-hidden rounded-3xl", tones[tone], className)} {...props} />;
}

export function CardHeader({ title, hint, actions }: { title: ReactNode; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-4 px-7 pb-2 pt-6">
      <div>
        <h3 className="font-display text-xl font-bold tracking-tight">{title}</h3>
        {hint && <p className="mt-1 max-w-2xl text-[13px] leading-relaxed text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export const CardBody = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-7 pb-7 pt-3", className)} {...props} />
);

/** Small uppercase label + large display number, like the stat tiles of the reference screens. */
export function Stat({ label, value, tone, hint }: { label: string; value: ReactNode; tone?: "bad" | "warn" | "ok"; hint?: ReactNode }) {
  const color = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-accent" : "text-ink";
  return (
    <div className="rounded-2xl bg-panel2 px-6 py-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-mute">{label}</div>
      <div className={cn("mt-2 font-display text-3xl font-semibold tracking-tight", color)}>{value}</div>
      {hint && <div className="mt-1 text-xs text-mute">{hint}</div>}
    </div>
  );
}

/** Square progress bar on a tinted track. */
export function Bar({ value, tone = "accent", className }: { value: number; tone?: "accent" | "ink" | "warn" | "bad"; className?: string }) {
  const fill = { accent: "bg-accent", ink: "bg-ink", warn: "bg-warn", bad: "bg-bad" }[tone];
  return (
    <div className={cn("h-2 w-full overflow-hidden bg-high", className)}>
      <div className={cn("h-full transition-all duration-500", fill)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

/** Square icon tile, as in the palette's icon buttons. */
export function IconTile({ children, tone = "accent", className }: { children: ReactNode; tone?: "accent" | "ink" | "warn" | "bad" | "info"; className?: string }) {
  const tones = {
    accent: "bg-accent/12 text-accent",
    ink: "bg-primary text-on-primary",
    warn: "bg-warn/14 text-warn",
    bad: "bg-bad/14 text-bad",
    info: "bg-info/14 text-info",
  };
  return <div className={cn("grid size-11 shrink-0 place-items-center rounded-[3px]", tones[tone], className)}>{children}</div>;
}
