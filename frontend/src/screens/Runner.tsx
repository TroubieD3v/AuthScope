import { Ban, Play, ShieldCheck, TriangleAlert } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Toggle } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type ModuleInfo, type Run } from "@/lib/api";
import { fmtTime, MODULE_LABEL } from "@/lib/utils";
import { PageHeader } from "./common";

export function Runner() {
  const { project, reload, go, setFocusRun } = useApp();
  const act = useAction();
  const [mods, setMods] = useState<{ modules: ModuleInfo[]; roadmap: { name: string; title: string }[] } | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [run, setRun] = useState<Run | null>(null);
  const [history, setHistory] = useState<Run[]>([]);
  const t = project.target;
  const [limits, setLimits] = useState({
    rps: t.rate_limit_rps, budget: t.max_requests, mutating: t.allow_mutating,
    resetPath: t.reset?.path ?? "", resetIdentity: t.reset?.identity ?? "", noReset: t.acknowledge_no_reset,
  });
  const timer = useRef<number | undefined>(undefined);

  const refreshHistory = useCallback(() => api.runs(project.id).then(setHistory), [project.id]);

  useEffect(() => {
    api.modules().then((m) => {
      setMods(m);
      setSelected(m.modules.map((x) => x.name).filter((n) => n !== "custom" || project.tests.length > 0));
    });
    api.runs(project.id).then((rs) => { setHistory(rs); const live = rs.find((r) => r.status === "running" || r.status === "queued"); if (live) setRun(live); });
  }, [project.id, project.tests.length]);

  useEffect(() => {
    window.clearInterval(timer.current);
    if (run && (run.status === "running" || run.status === "queued")) {
      timer.current = window.setInterval(async () => {
        const r = await api.run(run.id);
        setRun(r);
        if (r.status !== "running" && r.status !== "queued") { window.clearInterval(timer.current); refreshHistory(); }
      }, 600);
    }
    return () => window.clearInterval(timer.current);
  }, [run?.id, run?.status, refreshHistory]);

  const saveLimits = () => act(async () => {
    await api.saveProject(project.id, {
      ...project,
      target: {
        ...project.target, rate_limit_rps: Number(limits.rps), max_requests: Number(limits.budget), allow_mutating: limits.mutating,
        acknowledge_no_reset: limits.noReset,
        reset: limits.resetPath ? { method: "POST", path: limits.resetPath, identity: limits.resetIdentity || null } : null,
      },
    });
    await reload();
    return true;
  }, "Safety settings saved");

  const start = async () => {
    if (!(await saveLimits())) return;
    const r = await act(() => api.startRun(project.id, selected));
    if (r) setRun(r);
  };

  const active = run && (run.status === "running" || run.status === "queued");
  const pct = run && run.stats.total ? Math.round((run.stats.done / run.stats.total) * 100) : 0;
  const v = run?.stats.by_verdict ?? {};
  const missing = project.identities.filter((i) => i.secret_source === "missing");

  return (
    <div className="space-y-6">
      <PageHeader title="Test Runner" hint="Pick modules, review the safety limits, run." />

      {missing.length > 0 && (
        <div className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/10 px-4 py-2.5 text-sm text-warn">
          <TriangleAlert className="size-4" /> No token for {missing.map((m) => m.name).join(", ")} - their checks will be skipped. Set tokens in Identity Manager.
        </div>
      )}

      <div className="grid grid-cols-5 gap-4">
        <Card className="col-span-3">
          <CardHeader title="Modules" />
          <div className="divide-y divide-line">
            {mods?.modules.map((m) => (
              <label key={m.name} className="flex cursor-pointer items-start gap-3 px-5 py-3 hover:bg-panel2/40">
                <input type="checkbox" className="mt-1 size-4 accent-[#2dd4bf]" checked={selected.includes(m.name)}
                  onChange={(e) => setSelected(e.target.checked ? [...selected, m.name] : selected.filter((x) => x !== m.name))} />
                <div><div className="font-medium">{m.title}</div><div className="text-xs text-mute">{m.description}</div></div>
              </label>
            ))}
            {mods?.roadmap.map((m) => (
              <div key={m.name} className="flex items-center gap-3 px-5 py-2.5 opacity-50">
                <input type="checkbox" disabled className="size-4" /> <span>{m.title}</span><Badge>planned</Badge>
              </div>
            ))}
          </div>
        </Card>

        <Card className="col-span-2">
          <CardHeader title="Safety limits" hint="Requests go only to allowed hosts. Redirects are not followed." />
          <CardBody className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Max requests / second"><Input type="number" min={0.1} max={100} step={0.5} value={limits.rps} onChange={(e) => setLimits({ ...limits, rps: Number(e.target.value) })} /></Field>
              <Field label="Request budget per run"><Input type="number" min={1} value={limits.budget} onChange={(e) => setLimits({ ...limits, budget: Number(e.target.value) })} /></Field>
            </div>
            <div className="rounded-md border border-line bg-panel2/50 p-3">
              <Toggle checked={limits.mutating} onChange={(v) => setLimits({ ...limits, mutating: v })} label={<span className="font-medium">Allow state-changing requests (PUT/POST/DELETE)</span>} />
              <p className="mt-1 text-xs text-mute">Off by default. Use only with disposable test data and a reset endpoint.</p>
              {limits.mutating && (
                <div className="mt-3 space-y-2">
                  <Field label="Reset endpoint (POST)" hint="Called after every state-changing request"><Input className="font-mono" value={limits.resetPath} onChange={(e) => setLimits({ ...limits, resetPath: e.target.value })} placeholder="/__test/reset" /></Field>
                  <Field label="Reset as identity"><Input value={limits.resetIdentity} onChange={(e) => setLimits({ ...limits, resetIdentity: e.target.value })} placeholder="admin" /></Field>
                  {!limits.resetPath && <Toggle checked={limits.noReset} onChange={(v) => setLimits({ ...limits, noReset: v })} label="I accept that test data is not reset" />}
                </div>
              )}
            </div>
            <div className="flex gap-2 pt-1">
              {active ? (
                <Button variant="danger" onClick={() => act(() => api.cancelRun(run!.id), "Cancelling after in-flight requests")}><Ban className="size-4" /> Cancel run</Button>
              ) : (
                <Button disabled={selected.length === 0} onClick={start}><Play className="size-4" /> Start run ({selected.length})</Button>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      {run && (
        <Card>
          <CardHeader title={`Run ${run.id}`} hint={`${run.status} - started ${fmtTime(run.started_at)}`}
            actions={!active && <Button size="sm" onClick={() => { setFocusRun(run.id); go("findings"); }}><ShieldCheck className="size-3.5" /> Open findings</Button>} />
          <CardBody className="space-y-3">
            <div className="h-2.5 overflow-hidden rounded-full bg-panel2">
              <div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} />
            </div>
            <div className="flex flex-wrap gap-x-6 gap-y-1 font-mono text-xs">
              <span>{run.stats.done}/{run.stats.total} checks ({pct}%)</span>
              <span className="text-mute">{run.stats.requests} requests</span>
              <span className="text-bad">{v.violation ?? 0} violations</span>
              <span className="text-warn">{v.needs_review ?? 0} review</span>
              <span className="text-ok">{v.pass ?? 0} passed</span>
              <span className="text-info">{v.inconclusive ?? 0} inconclusive</span>
              <span className="text-mute">{v.skipped ?? 0} skipped</span>
            </div>
            {run.error && <p className="text-sm text-bad">{run.error}</p>}
            {(run.extra.warnings ?? []).map((w) => <p key={w} className="text-xs text-warn">{w}</p>)}
          </CardBody>
        </Card>
      )}

      <Card>
        <CardHeader title="Previous runs" />
        <table className="w-full text-left text-sm">
          <tbody>
            {history.length === 0 && <tr><td className="px-5 py-4 text-mute">No runs yet.</td></tr>}
            {history.map((r) => (
              <tr key={r.id} className="cursor-pointer border-t border-line first:border-0 hover:bg-panel2/50" onClick={() => { setFocusRun(r.id); go("findings"); }}>
                <td className="px-5 py-2 font-mono text-xs">{r.id}</td>
                <td className="text-mute">{fmtTime(r.started_at)}</td>
                <td className="text-xs text-mute">{r.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ")}</td>
                <td><Badge tone={r.status === "completed" ? "ok" : r.status === "failed" ? "bad" : "mute"}>{r.status}</Badge></td>
                <td className="pr-5 text-right font-mono text-xs text-bad">{r.stats.by_verdict.violation ?? 0} violations</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
    </div>
  );
}
