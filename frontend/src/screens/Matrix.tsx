import { useCallback, useEffect, useState } from "react";
import { Method } from "@/components/ui/badge";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { useAction, useApp } from "@/ctx";
import { api, type Matrix as M, type MatrixCell } from "@/lib/api";
import { cn } from "@/lib/utils";
import { PageHeader } from "./common";

const EXPECT: Record<string, { sym: string; cls: string; title: string }> = {
  allow: { sym: "allow", cls: "text-accent", title: "Expected: allowed" },
  deny: { sym: "deny", cls: "text-mute", title: "Expected: denied" },
  conditional: { sym: "own only", cls: "text-info", title: "Expected: allowed only for the owner / same tenant" },
  off: { sym: "off", cls: "text-mute/40", title: "Endpoint excluded from tests" },
};

function cellStyle(c: MatrixCell) {
  switch (c.worst) {
    case "violation": case "error": return "bg-bad/20 ring-1 ring-inset ring-bad/50";
    case "needs_review": return "bg-warn/15 ring-1 ring-inset ring-warn/40";
    case "pass": return "bg-ok/8 ring-1 ring-inset ring-ok/20";
    case "inconclusive": return "bg-info/10 ring-1 ring-inset ring-info/25";
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

  return (
    <div className="space-y-10">
      <PageHeader kicker={m.run_id ? "Verified by run " + m.run_id : "Expected access"} kickerTone={m.run_id ? "accent" : "mute"} title="Permission Matrix"
        hint={m.run_id ? `Expected access (from your rules) overlaid with the results of run ${m.run_id}.` : "Expected access derived from endpoint rules. Run a test to overlay real results."} />
      <Card>
        <CardHeader title="Authorization matrix" hint="Click a cell to override the expectation (allow -> deny -> back to the derived rule)." />
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="text-left text-xs text-mute">
                <th className="px-5 py-2.5 font-medium">Endpoint</th>
                {m.identities.map((i) => (
                  <th key={i.name} className="px-2 py-2.5 text-center font-medium">
                    <div className="text-ink">{i.name}</div>
                    <div className="text-[10px] font-normal">{i.role}{i.tenant ? ` - ${i.tenant}` : ""}</div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {m.rows.map((r) => (
                <tr key={r.endpoint} className={cn("border-t border-line", !r.enabled && "opacity-40")}>
                  <td className="px-5 py-2"><Method m={r.method} /><span className="font-mono text-[13px]">{r.path}</span>
                    <span className="ml-2 text-[10px] uppercase tracking-wide text-mute">{r.access}{r.inferred ? " (inferred)" : ""}</span></td>
                  {m.identities.map((i) => {
                    const c = r.cells[i.name];
                    const e = EXPECT[c.expected];
                    const tested = Object.entries(c.actual).filter(([k]) => k !== "skipped");
                    return (
                      <td key={i.name} className="p-1 text-center">
                        <button disabled={!r.enabled} onClick={() => cycle(r.endpoint, i.name, c)}
                          title={`${e.title}${c.overridden ? " (manual override)" : ""}\n${tested.map(([k, n]) => `${k}: ${n}`).join(", ") || "not tested yet"}`}
                          className={cn("relative h-11 w-full min-w-[84px] cursor-pointer rounded-[3px] text-xs font-semibold transition hover:brightness-110", cellStyle(c))}>
                          <span className={e.cls}>{e.sym}</span>
                          {c.worst === "violation" && <span className="block text-[10px] font-semibold text-bad">VIOLATION</span>}
                          {c.worst === "needs_review" && <span className="block text-[10px] font-semibold text-warn">REVIEW</span>}
                          {c.worst === "pass" && <span className="block text-[10px] text-ok">verified</span>}
                          {c.overridden && <span className="absolute right-1 top-1 size-1.5 rounded-full bg-accent" title="manual override" />}
                        </button>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <CardBody className="flex flex-wrap gap-x-6 gap-y-2 border-t border-line text-xs text-mute">
          <Legend cls="text-accent" label="expected allowed" /><Legend cls="text-mute" label="expected denied" />
          <Legend cls="bg-bad/40" label="policy violation" box /><Legend cls="bg-warn/40" label="needs review" box />
          <Legend cls="bg-ok/30" label="verified as expected" box /><Legend cls="bg-accent" label="manual override" box />
        </CardBody>
      </Card>
    </div>
  );
}

const Legend = ({ cls, label, box }: { cls: string; label: string; box?: boolean }) => (
  <span className="flex items-center gap-1.5">
    {box ? <span className={cn("size-3 rounded-sm", cls)} /> : <span className={cn("font-medium", cls)}>aa</span>} {label}
  </span>
);
