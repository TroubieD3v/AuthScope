import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

const tones = {
  bad: "bg-bad/15 text-bad border-bad/30",
  warn: "bg-warn/15 text-warn border-warn/30",
  ok: "bg-ok/15 text-ok border-ok/30",
  info: "bg-info/15 text-info border-info/30",
  mute: "bg-panel2 text-mute border-line",
  accent: "bg-accent/15 text-accent border-accent/30",
};

export function Badge({ tone = "mute", className, ...props }: HTMLAttributes<HTMLSpanElement> & { tone?: keyof typeof tones }) {
  return (
    <span
      className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium leading-4", tones[tone], className)}
      {...props}
    />
  );
}

const methodColors: Record<string, string> = {
  GET: "text-info", POST: "text-ok", PUT: "text-warn", PATCH: "text-warn", DELETE: "text-bad",
};
export const Method = ({ m }: { m: string }) => (
  <span className={cn("inline-block w-14 font-mono text-xs font-semibold", methodColors[m] ?? "text-mute")}>{m}</span>
);
