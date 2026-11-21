import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/api";
import { VERDICT_META } from "@/lib/utils";

/** Screen toolbar: title, an optional state label, one line of context and the screen's actions. */
export function PageHeader({ title, hint, actions, kicker, kickerTone = "mute" }: {
  title: string; hint?: ReactNode; actions?: ReactNode; kicker?: string;
  kickerTone?: "accent" | "warn" | "bad" | "mute" | "info" | "ok";
}) {
  return (
    <section className="flex flex-wrap items-center justify-between gap-3 border-b border-line pb-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <h1 className="text-[15px] font-semibold">{title}</h1>
          {kicker && <Badge tone={kickerTone}>{kicker}</Badge>}
        </div>
        {hint && <p className="mt-0.5 max-w-4xl text-xs text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-1.5">{actions}</div>}
    </section>
  );
}

export const VerdictBadge = ({ v }: { v: Verdict }) => <Badge tone={VERDICT_META[v].tone}>{VERDICT_META[v].label}</Badge>;

export function SectionTitle({ title, hint, actions }: { title: string; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <h2 className="text-[13px] font-semibold">{title}</h2>
        {hint && <p className="text-xs text-mute">{hint}</p>}
      </div>
      {actions}
    </div>
  );
}

/** Small square that encodes severity in tables. */
export function SevMark({ s }: { s: string }) {
  const cls = s === "critical" || s === "high" ? "bg-bad" : s === "medium" ? "bg-warn" : s === "low" ? "bg-info" : "border border-dim";
  return <span className={`mr-1.5 inline-block size-2 align-[1px] ${cls}`} />;
}
