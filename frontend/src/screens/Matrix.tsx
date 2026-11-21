import { useCallback, useEffect, useState } from "react";
import { Method } from "@/components/ui/badge";
import { Card, CardHeader } from "@/components/ui/card";
import { useAction, useApp } from "@/ctx";
import { api, type Matrix as M, type MatrixCell } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader } from "./common";

const EXPECT: Record<string, { sym: string; cls: string; title: string }> = {
  allow: { sym: "allow", cls: "text-ink", title: "Expected: allowed" },
  deny: { sym: "deny", cls: "text-mute", title: "Expected: denied" },
  conditional: { sym: "own only", cls: "text-ink", title: "Expected: allowed only for the owner / same tenant" },
  off: { sym: "off", cls: "text-dim", title: "Endpoint excluded from tests" },
};

function cellStyle(c: MatrixCell) {
  switch (c.worst) {
    case "violation": case "error": return "bg-bad/12 shadow-[inset_3px_0_0_var(--bad)]";
    case "needs_review": return "bg-warn/12 shadow-[inset_3px_0_0_var(--warn)]";
    case "inconclusive": return "bg-info/10";
    default: return "";
  }
}

export function Matrix() {
  const { project, reload } = useApp();
  const act = useAction();
  const [m, setM] = useState<M | null>(null);

  const load = useCallback(() => api.matrix(project.id).then(setM), [project.id, project.overrides]);
  useEffect(() => { load(); }, [load]);

  const cycle = (endpoint: string, identity: string, c: MatrixCell) => act(async () => {
    // default -> force allow -> force deny -> default
    const cur = project.overrides.find((o) => o.endpoint === endpoint && o.identity === identity && o.resource === null);
    if (!cur) await api.putOverride(project.id, { endpoint, identity, resource: null, expected: c.expected === "deny" ? "allow" : "deny" });
    else if (cur.expected === "allow" && c.expected !== "deny") await api.putOverride(project.id, { ...cur, expected: "deny" });
    else await api.putOverride(project.id, cur, true);
    await reload();
  });

  if (!m) return <div className="text-mute">Loading...</div>;
  const violations = m.rows.reduce((a, r) => a + Object.values(r.cells).filter((c) => c.worst === "violation").length, 0);

  return (
    <div className="space-y-3">
      <PageHeader kicker={m.run_id ? "Verified by run " + m.run_id : "Expected access"} kickerTone={m.run_id ? (violations ? "bad" : "ok") : "mute"} title="Permission Matrix"
        hint={m.run_id ? `Expected access (from your rules) overlaid with the results of run ${m.run_id}.` : "Expected access derived from endpoint rules. Run a test to overlay real results."} />
      <Card>
        <CardHeader title="Authorization matrix" hint="Click a cell to override the expectation (allow -> deny -> back to the derived rule)."
          actions={
            <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-mute">
              <Legend cls="bg-bad/20 shadow-[inset_3px_0_0_var(--bad)]" label="policy violation" />
              <Legend cls="bg-warn/20 shadow-[inset_3px_0_0_var(--warn)]" label="needs review" />
              <Legend cls="border border-line" label="verified / not tested" />
              <Legend cls="bg-ink" label="manual override" dot />
            </div>
          } />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr className="bg-panel2/40 text-left text-xs text-mute">
                <th className="border-b border-line px-3 py-1.5 font-medium">Endpoint</th>
                {m.identities.map((i) => (
                  <th key={i.name} className="w-[104px] border-b border-l border-line2 border-b-line px-2 py-1.5 font-medium">
                    <div className="font-semibold text-ink">{i.name}</div>
                    <div className="text-[11px] font-normal">{i.role}{i.tenant ? ` · ${i.tenant}` : ""}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {m.rows.map((r) => (
                <tr key={r.endpoint} className={cn("border-b border-line2 last:border-b-0", !r.enabled && "opacity-40")}>
                  <td className="whitespace-nowrap px-3 py-0"><Method m={r.method} /><span className="font-mono text-[12px]">{r.path}</span>
                    <span className="ml-2 text-[11px] text-dim">{r.access}{r.inferred ? " (inferred)" : ""}</span></td>
                  {m.identities.map((i) => {
                    const c = r.cells[i.name];
                    const e = EXPECT[c.expected];
                    const tested = Object.entries(c.actual).filter(([k]) => k !== "skipped");
                    return (
                      <td key={i.name} className="border-l border-line2 p-0">
                        <button disabled={!r.enabled} onClick={() => cycle(r.endpoint, i.name, c)}
                          title={`${e.title}${c.overridden ? " (manual override)" : ""}\n${tested.map(([k, n]) => `${k}: ${n}`).join(", ") || "not tested yet"}`}
                          className={cn("relative block h-[38px] w-full cursor-pointer px-2 text-left leading-tight transition-colors hover:bg-panel2", cellStyle(c))}>
                          <span className={cn("block", c.worst === "violation" ? "text-bad" : e.cls)}>{e.sym}</span>
                          {c.worst === "violation" && <span className="block text-[10.5px] font-medium text-bad">VIOLATION</span>}
                          {c.worst === "needs_review" && <span className="block text-[10.5px] font-medium text-warn">REVIEW</span>}
                          {c.worst === "pass" && <span className="block text-[10.5px] text-ok">verified</span>}
                          {!c.worst && <span className="block text-[10.5px] text-dim">not tested</span>}
                          {c.overridden && <span className="absolute right-1.5 top-1.5 size-1.5 bg-ink" title="manual override" />}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}

const Legend = ({ cls, label, dot }: { cls: string; label: string; dot?: boolean }) => (
  <span className="flex items-center gap-1.5">
    <span className={cn(dot ? "size-1.5" : "size-3", cls)} /> {label}
  </span>
);
