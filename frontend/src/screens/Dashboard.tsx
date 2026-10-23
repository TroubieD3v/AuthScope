import { useEffect, useState } from "react";
import { Play } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, Stat } from "@/components/ui/card";
import { useApp } from "@/ctx";
import { api, type CheckResult, type Dashboard as Dash } from "@/lib/api";
import { fmtTime, MODULE_LABEL, SEVERITY_TONE } from "@/lib/utils";
import { PageHeader } from "./common";

export function Dashboard() {
  const { project, go, setFocusRun } = useApp();
  const [d, setD] = useState<Dash | null>(null);
  const [top, setTop] = useState<CheckResult[]>([]);

  useEffect(() => {
    api.dashboard(project.id).then(async (dash) => {
      setD(dash);
      if (dash.latest_run) setTop((await api.results(dash.latest_run.id, "findings")).slice(0, 5));
    });
  }, [project.id]);

  if (!d) return <div className="text-mute">Loading...</div>;
  const v = d.verdicts;
  const findings = (v.violation ?? 0) + (v.needs_review ?? 0);
  const modules = Object.entries(d.modules);

  return (
    <div className="space-y-6">
      <PageHeader title="Dashboard" hint={`${project.name} - ${project.target.base_url}`}
        actions={<Button onClick={() => go("runner")}><Play className="size-4" /> New test run</Button>} />

      <div className="grid grid-cols-4 gap-4">
        <Stat label="Endpoints" value={d.endpoints} />
        <Stat label="Test identities" value={d.identities} />
        <Stat label="Findings" value={d.latest_run ? findings : "-"} tone={findings ? "bad" : undefined} />
        <Stat label="Checks passed" value={d.latest_run ? (v.pass ?? 0) : "-"} tone={d.latest_run ? "ok" : undefined} />
      </div>

      {!d.latest_run ? (
        <Card><CardBody className="py-10 text-center text-mute">
          No test runs yet. Add identities and resources, review the Permission Matrix, then start a run.
        </CardBody></Card>
      ) : (
        <div className="grid grid-cols-5 gap-4">
          <Card className="col-span-3">
            <CardHeader title="Results by module" hint={`Run ${d.latest_run.id} - ${fmtTime(d.latest_run.started_at)}`} />
            <CardBody className="space-y-3">
              {modules.map(([m, c]) => {
                const total = Object.values(c).reduce((a, b) => a + b, 0) || 1;
                const seg = (k: string, cls: string) => c[k] ? <div title={`${k}: ${c[k]}`} className={cls} style={{ width: `${(c[k] / total) * 100}%` }} /> : null;
                return (
                  <div key={m}>
                    <div className="mb-1 flex justify-between text-xs">
                      <span className="font-medium">{MODULE_LABEL[m] ?? m}</span>
                      <span className="font-mono text-mute">
                        {c.violation ?? 0} violations - {c.needs_review ?? 0} review - {c.pass ?? 0} passed
                      </span>
                    </div>
                    <div className="flex h-2 overflow-hidden rounded-full bg-panel2">
                      {seg("violation", "bg-bad")}{seg("needs_review", "bg-warn")}{seg("pass", "bg-ok")}
                      {seg("inconclusive", "bg-info/60")}{seg("skipped", "bg-line")}
                    </div>
                  </div>
                );
              })}
            </CardBody>
          </Card>
          <Card className="col-span-2">
            <CardHeader title="Top findings" actions={<Button size="sm" variant="ghost" onClick={() => { setFocusRun(d.latest_run!.id); go("findings"); }}>View all</Button>} />
            <CardBody className="space-y-2.5">
              {top.length === 0 && <p className="text-sm text-ok">No violations in the latest run.</p>}
              {top.map((f) => (
                <div key={f.id} className="rounded-md border border-line bg-panel2/60 p-2.5">
                  <div className="mb-1 flex items-center gap-2">
                    <Badge tone={SEVERITY_TONE[f.severity]}>{f.severity}</Badge>
                    <span className="text-[11px] text-mute">{MODULE_LABEL[f.module]}</span>
                  </div>
                  <div className="text-xs leading-snug">{f.name}</div>
                </div>
              ))}
            </CardBody>
          </Card>
        </div>
      )}

      <Card>
        <CardHeader title="Run history" />
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-mute"><tr>
            <th className="px-5 py-2 font-medium">Run</th><th className="font-medium">Started</th><th className="font-medium">Status</th>
            <th className="font-medium">Violations</th><th className="font-medium">Review</th><th className="font-medium">Passed</th>
          </tr></thead>
          <tbody>
            {d.history.length === 0 && <tr><td colSpan={6} className="px-5 py-4 text-mute">Nothing yet.</td></tr>}
            {d.history.map((r) => (
              <tr key={r.id} className="cursor-pointer border-t border-line hover:bg-panel2/50" onClick={() => { setFocusRun(r.id); go("findings"); }}>
                <td className="px-5 py-2 font-mono text-xs">{r.id}</td>
                <td className="text-mute">{fmtTime(r.started_at)}</td>
                <td><Badge tone={r.status === "completed" ? "ok" : r.status === "failed" ? "bad" : "mute"}>{r.status}</Badge></td>
                <td className="font-mono text-bad">{r.violations}</td>
                <td className="font-mono text-warn">{r.review}</td>
                <td className="font-mono text-ok">{r.passed}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
