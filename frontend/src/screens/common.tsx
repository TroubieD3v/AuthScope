import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/api";
import { cn, VERDICT_META } from "@/lib/utils";

/** Editorial page header: a status pill, a large headline and a lead paragraph. */
export function PageHeader({ title, hint, actions, kicker, kickerTone = "accent" }: {
  title: string; hint?: ReactNode; actions?: ReactNode; kicker?: string;
  kickerTone?: "accent" | "warn" | "bad" | "mute" | "info";
}) {
  return (
    <section className="flex flex-col gap-6 md:flex-row md:items-end md:justify-between">
      <div className="max-w-2xl">
        {kicker && <Badge tone={kickerTone} className="mb-4">{kicker}</Badge>}
        <h1 className="font-display text-4xl font-semibold leading-none tracking-[-0.03em] md:text-5xl">{title}</h1>
        {hint && <p className="mt-4 text-[15px] leading-relaxed text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </section>
  );
}

export const VerdictBadge = ({ v }: { v: Verdict }) => <Badge tone={VERDICT_META[v].tone}>{VERDICT_META[v].label}</Badge>;

/** Two concentric rings, like the reference dashboard dial. Values are 0..1. */
export function Dial({ outer, inner, children, className }: { outer: number; inner: number; children: ReactNode; className?: string }) {
  const C = 2 * Math.PI * 45;
  return (
    <div className={cn("relative grid size-72 place-items-center md:size-80", className)}>
      <div className="absolute inset-6 rounded-full bg-accent/10 blur-3xl" />
      <svg className="absolute size-full -rotate-90" viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="45" fill="none" stroke="var(--surface-container)" strokeWidth="5" />
        <circle cx="50" cy="50" r="45" fill="none" stroke="var(--accent)" strokeWidth="5" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - outer)} style={{ transition: "stroke-dashoffset .8s ease" }} />
      </svg>
      <svg className="absolute size-3/4 -rotate-90" viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r="45" fill="none" stroke="var(--surface-high)" strokeWidth="7" />
        <circle cx="50" cy="50" r="45" fill="none" stroke="var(--bad)" strokeWidth="7" strokeLinecap="round"
          strokeDasharray={C} strokeDashoffset={C * (1 - inner)} style={{ transition: "stroke-dashoffset .8s ease" }} />
      </svg>
      <div className="relative z-10 text-center">{children}</div>
    </div>
  );
}

export function SectionTitle({ title, hint, actions }: { title: string; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4 px-1">
      <div>
        <h2 className="font-display text-2xl font-bold tracking-tight">{title}</h2>
        {hint && <p className="mt-0.5 text-sm text-mute">{hint}</p>}
      </div>
      {actions}
    </div>
  );
}
