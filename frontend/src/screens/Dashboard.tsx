import { Play } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Bar, Card, CardHeader, Stat } from "@/components/ui/card";
import { useApp } from "@/ctx";
import { api, type CheckResult, type Dashboard as Dash } from "@/lib/api";
import { cn, fmtTime, MODULE_LABEL, VERDICT_META } from "@/lib/utils";
import { PageHeader, SevMark } from "./common";

const th = "whitespace-nowrap border-b border-line px-2 py-1.5 text-left text-xs font-medium text-mute";
const td = "whitespace-nowrap px-2 py-1";

export function Dashboard() {
  const { project, go, setFocusRun } = useApp();
  const [d, setD] = useState<Dash | null>(null);
  const [top, setTop] = useState<CheckResult[]>([]);

  useEffect(() => {
    api.dashboard(project.id).then(async (dash) => {
      setD(dash);
      if (dash.latest_run) setTop((await api.results(dash.latest_run.id, "findings")).slice(0, 12));
    });
  }, [project.id]);

  if (!d) return <div className="text-mute">Loading...</div>;
  const v = d.verdicts;
  const violations = v.violation ?? 0;
  const review = v.needs_review ?? 0;
  const tested = Object.entries(v).filter(([k]) => k !== "skipped").reduce((a, [, n]) => a + n, 0);
  const passed = v.pass ?? 0;
  const run = d.latest_run;
  const openRun = (id: string) => { setFocusRun(id); go("findings"); };

  return (
    <div className="space-y-3">
      <PageHeader
        kicker={!run ? "No runs yet" : violations ? "Action needed" : "Policy holds"}
        kickerTone={!run ? "mute" : violations ? "bad" : "ok"}
        title="Authorization posture"
        hint={run
          ? <>The last run checked {tested} cases across {d.endpoints} endpoints.{" "}
              {violations ? <><span className="text-bad">{violations} break your policy</span>{review ? `, ${review} need review.` : "."}</> : "Nothing breaks your policy."}</>
          : "Add identities and objects, review the Permission Matrix, then start a run."}
        actions={<Button onClick={() => go("runner")}><Play className="size-3.5" /> New test run</Button>}
      />

      {/* Counters */}
      <div className="grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-3 xl:grid-cols-6">
        <Stat label="Endpoints" value={d.endpoints} />
        <Stat label="Test identities" value={d.identities} />
        <Stat label="Test objects" value={d.resources} />
        <Stat label="Policy violations" value={run ? violations : "-"} tone={run && violations ? "bad" : undefined} />
        <Stat label="Needs review" value={run ? review : "-"} tone={run && review ? "warn" : undefined} />
        <Stat label="Checks passed" value={run ? `${passed}/${tested}` : "-"} tone={run ? "ok" : undefined} />
      </div>

      <div className="grid gap-3 xl:grid-cols-2">
        {run ? (
          <Card>
            <CardHeader title="Results by module" hint={`Run ${run.id} - ${fmtTime(run.started_at)}`} />
            <table className="w-full border-collapse text-[12.5px]">
              <thead><tr><th className={th}>Module</th><th className={cn(th, "text-right")}>Passed</th><th className={cn(th, "text-right")}>Violations</th><th className={cn(th, "text-right")}>Review</th><th className={cn(th, "w-1/3")}>Pass rate</th></tr></thead>
              <tbody>
                {Object.entries(d.modules).map(([m, c]) => {
                  const total = Object.entries(c).filter(([k]) => k !== "skipped").reduce((a, [, n]) => a + n, 0) || 1;
                  const bad = c.violation ?? 0;
                  return (
                    <tr key={m} className="border-b border-line2 last:border-b-0">
                      <td className={td}>{MODULE_LABEL[m] ?? m}</td>
                      <td className={cn(td, "text-right font-mono text-[12px]")}>{c.pass ?? 0}<span className="text-dim">/{total}</span></td>
                      <td className={cn(td, "text-right font-mono text-[12px]", bad ? "text-bad" : "text-dim")}>{bad}</td>
                      <td className={cn(td, "text-right font-mono text-[12px]", c.needs_review ? "text-warn" : "text-dim")}>{c.needs_review ?? 0}</td>
                      <td className={td}><Bar value={((c.pass ?? 0) / total) * 100} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </Card>
        ) : (
          <Card><CardHeader title="Results by module" /><p className="px-3 py-4 text-xs text-mute">Results appear here after the first run.</p></Card>
        )}

        <Card>
          <CardHeader title="Issue activity" hint={run ? `Latest run ${run.id}` : undefined}
            actions={run && <Button size="sm" variant="ghost" onClick={() => openRun(run.id)}>View all</Button>} />
          {!run && <p className="px-3 py-4 text-xs text-mute">Findings appear here after the first run.</p>}
          {run && top.length === 0 && <p className="px-3 py-4 text-xs text-ok">No violations in the latest run.</p>}
          {top.length > 0 && (
            <table className="w-full border-collapse text-[12.5px]">
              <thead><tr><th className={th}>Severity</th><th className={th}>Verdict</th><th className={th}>Check</th></tr></thead>
              <tbody>
                {top.map((f) => (
                  <tr key={f.id} onClick={() => openRun(run!.id)} className="cursor-pointer border-b border-line2 last:border-b-0 hover:bg-panel2/70">
                    <td className={td}><SevMark s={f.severity} />{f.severity}</td>
                    <td className={cn(td, f.verdict === "violation" ? "text-bad" : "text-warn")}>{VERDICT_META[f.verdict].label}</td>
                    <td className="max-w-0 w-full truncate px-2 py-1 font-mono text-[12px]" title={f.name}>{f.name}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
      </div>

      <Card>
        <CardHeader title="Run history" />
        {d.history.length === 0 ? <p className="px-3 py-4 text-xs text-mute">Nothing yet.</p> : (
          <table className="w-full border-collapse text-[12.5px]">
            <thead><tr><th className={th}>Run</th><th className={th}>Started</th><th className={th}>Status</th><th className={cn(th, "text-right")}>Violations</th><th className={cn(th, "text-right")}>Review</th><th className={cn(th, "text-right")}>Passed</th></tr></thead>
            <tbody>
              {d.history.map((r) => (
                <tr key={r.id} onClick={() => openRun(r.id)} className="cursor-pointer border-b border-line2 last:border-b-0 hover:bg-panel2/70">
                  <td className={cn(td, "font-mono text-[12px]")}>{r.id}</td>
                  <td className={cn(td, "text-mute")}>{fmtTime(r.started_at)}</td>
                  <td className={td}>{r.status}</td>
                  <td className={cn(td, "text-right font-mono text-[12px]", r.violations ? "text-bad" : "text-dim")}>{r.violations}</td>
                  <td className={cn(td, "text-right font-mono text-[12px]", r.review ? "text-warn" : "text-dim")}>{r.review}</td>
                  <td className={cn(td, "text-right font-mono text-[12px] text-ok")}>{r.passed}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
