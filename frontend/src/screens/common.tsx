import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import type { Verdict } from "@/lib/api";
import { VERDICT_META } from "@/lib/utils";

export function PageHeader({ title, hint, actions }: { title: string; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {hint && <p className="mt-0.5 text-sm text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export const VerdictBadge = ({ v }: { v: Verdict }) => <Badge tone={VERDICT_META[v].tone}>{VERDICT_META[v].label}</Badge>;
