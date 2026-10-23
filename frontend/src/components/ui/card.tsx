import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/utils";

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("rounded-xl border border-line bg-panel/90 backdrop-blur", className)} {...props} />;
}

export function CardHeader({ title, hint, actions }: { title: ReactNode; hint?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-3.5">
      <div>
        <h3 className="text-[13px] font-semibold uppercase tracking-wider text-ink">{title}</h3>
        {hint && <p className="mt-0.5 text-xs text-mute">{hint}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export const CardBody = ({ className, ...props }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("p-5", className)} {...props} />
);

export function Stat({ label, value, tone }: { label: string; value: ReactNode; tone?: "bad" | "warn" | "ok" }) {
  const color = tone === "bad" ? "text-bad" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <Card className="px-5 py-4">
      <div className="text-xs uppercase tracking-wider text-mute">{label}</div>
      <div className={cn("mt-1 font-mono text-3xl font-semibold", color)}>{value}</div>
    </Card>
  );
}
