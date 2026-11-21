import { Ban, Building2, EyeOff, Lock, Play, ShieldCheck, Shuffle, TriangleAlert, UserX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bar, Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Switch, Toggle } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type ModuleInfo, type Run } from "@/lib/api";
import { cn, fmtTime, MODULE_LABEL } from "@/lib/utils";
import { PageHeader } from "./common";

const ICONS: Record<string, typeof Lock> = {
  bola: Shuffle, bfla: Lock, bopla: EyeOff, unauth: UserX, tenant: Building2, custom: ShieldCheck,
};

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
  const th = "whitespace-nowrap border-b border-line px-2 py-1.5 text-left text-xs font-medium text-mute";

  return (
    <div className="space-y-3">
      <PageHeader
        kicker={active ? "Running" : "Read-only by default"} kickerTone={active ? "warn" : "mute"}
        title="Test Runner"
        hint={<>Choose the checks, review the safety limits and run. {selected.length} modules are selected;
          requests go only to <span className="font-mono text-ink">{project.target.allowed_hosts.join(", ")}</span>.</>}
        actions={active ? (
          <Button variant="danger" onClick={() => act(() => api.cancelRun(run!.id), "Cancelling after in-flight requests")}><Ban className="size-3.5" /> Cancel run</Button>
        ) : (
          <Button disabled={selected.length === 0} onClick={start}><Play className="size-3.5" /> Start run ({selected.length})</Button>
        )}
      />

      {missing.length > 0 && (
        <div className="flex items-center gap-2 border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-warn">
          <TriangleAlert className="size-3.5 shrink-0" /> No token for {missing.map((m) => m.name).join(", ")} - their checks will be skipped. Set tokens in Identity Manager.
        </div>
      )}

      {run && (
        <Card>
          <CardHeader
            title={<span className="flex items-center gap-2">Run <span className="font-mono font-medium">{run.id}</span>
              <Badge tone={run.status === "completed" ? "ok" : run.status === "failed" ? "bad" : active ? "warn" : "mute"}>{run.status}</Badge></span>}
            hint={`Started ${fmtTime(run.started_at)}`}
            actions={!active && <Button size="sm" onClick={() => { setFocusRun(run.id); go("findings"); }}><ShieldCheck className="size-3.5" /> Open findings</Button>}
          />
          <div className="px-3 py-2.5">
            <div className="h-1.5 w-full overflow-hidden bg-high"><div className="h-full bg-accent transition-all" style={{ width: `${pct}%` }} /></div>
            <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 text-xs">
              <span className="font-mono text-ink">{run.stats.done}/{run.stats.total} checks ({pct}%)</span>
              <span className="text-mute">{run.stats.requests} requests{run.stats.retries ? ` · ${run.stats.retries} retries (${run.stats.backoff_s}s back-off)` : ""}</span>
              <span className="text-bad">{v.violation ?? 0} violations</span>
              <span className="text-warn">{v.needs_review ?? 0} review</span>
              <span className="text-ok">{v.pass ?? 0} passed</span>
              <span className="text-mute">{v.inconclusive ?? 0} inconclusive</span>
              <span className="text-mute">{v.skipped ?? 0} skipped</span>
            </div>
            {run.error && <p className="mt-2 text-xs text-bad">{run.error}</p>}
            {(run.extra.warnings ?? []).map((w) => <p key={w} className="mt-1 text-xs text-warn">{w}</p>)}
          </div>
        </Card>
      )}

      <div className="grid gap-3 xl:grid-cols-[minmax(0,1fr)_360px]">
        <Card>
          <CardHeader title="Modules" hint="Each module records what passed, not only what failed." />
          <ul>
            {mods?.modules.map((m) => {
              const Icon = ICONS[m.name] ?? ShieldCheck;
              const on = selected.includes(m.name);
              return (
                <li key={m.name} className={cn("flex items-start gap-3 border-b border-line2 px-3 py-2.5 last:border-b-0", on && "bg-panel2/40")}>
                  <div className="pt-0.5">
                    <Switch checked={on} label={m.title}
                      onChange={(c) => setSelected(c ? [...selected, m.name] : selected.filter((x) => x !== m.name))} />
                  </div>
                  <Icon className={cn("mt-0.5 size-4 shrink-0", on ? "text-ink" : "text-dim")} />
                  <div className="min-w-0">
                    <h3 className="text-[12.5px] font-semibold">{m.title}</h3>
                    <p className="text-xs leading-relaxed text-mute">{m.description}</p>
                  </div>
                </li>
              );
            })}
            {mods?.roadmap.map((m) => (
              <li key={m.name} className="flex items-center gap-3 border-t border-line2 px-3 py-2 text-xs text-dim">
                <span className="size-4 shrink-0 border border-dashed border-dim" />{m.title}<Badge className="ml-auto">planned</Badge>
              </li>
            ))}
          </ul>
        </Card>

        <Card className="self-start">
          <CardHeader title="Safety limits" hint="Requests go only to allowed hosts, one validated address per request. Redirects are not followed." />
          <CardBody className="space-y-3">
            <div className="grid grid-cols-2 gap-2">
              <Field label="Requests / second"><Input type="number" min={0.1} max={100} step={0.5} value={limits.rps} onChange={(e) => setLimits({ ...limits, rps: Number(e.target.value) })} /></Field>
              <Field label="Budget per run"><Input type="number" min={1} value={limits.budget} onChange={(e) => setLimits({ ...limits, budget: Number(e.target.value) })} /></Field>
            </div>
            <div className="border border-line2 bg-bg p-2.5">
              <Toggle checked={limits.mutating} onChange={(x) => setLimits({ ...limits, mutating: x })} label={<span className="font-medium">Allow state-changing requests</span>} />
              <p className="mt-1.5 text-xs text-mute">PUT / POST / DELETE. Off by default; use only with disposable test data and a reset endpoint.</p>
              {limits.mutating && (
                <div className="mt-3 space-y-2">
                  <Field label="Reset endpoint (POST)" hint="Called after every state-changing request"><Input className="font-mono" value={limits.resetPath} onChange={(e) => setLimits({ ...limits, resetPath: e.target.value })} placeholder="/__test/reset" /></Field>
                  <Field label="Reset as identity"><Input value={limits.resetIdentity} onChange={(e) => setLimits({ ...limits, resetIdentity: e.target.value })} placeholder="admin" /></Field>
                  {!limits.resetPath && <Toggle checked={limits.noReset} onChange={(x) => setLimits({ ...limits, noReset: x })} label="I accept that test data is not reset" />}
                </div>
              )}
            </div>
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title="Previous runs" />
        {history.length === 0 ? <p className="px-3 py-4 text-xs text-mute">No runs yet.</p> : (
          <table className="w-full border-collapse text-[12.5px]">
            <thead>
              <tr>
                <th className={th}>Run</th><th className={th}>Started</th><th className={th}>Status</th><th className={th}>Modules</th>
                <th className={cn(th, "text-right")}>Violations</th><th className={cn(th, "w-48")}>Pass rate</th>
              </tr>
            </thead>
            <tbody>
              {history.map((r) => {
                const total = Object.values(r.stats.by_verdict).reduce((a, n) => a + n, 0) || 1;
                return (
                  <tr key={r.id} onClick={() => { setFocusRun(r.id); go("findings"); }} className="cursor-pointer border-b border-line2 last:border-b-0 hover:bg-panel2/70">
                    <td className="px-2 py-1 font-mono text-[12px]">{r.id}</td>
                    <td className="whitespace-nowrap px-2 py-1 text-mute">{fmtTime(r.started_at)}</td>
                    <td className="px-2 py-1">{r.status}</td>
                    <td className="max-w-0 w-full truncate px-2 py-1 text-mute">{r.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ")}</td>
                    <td className={cn("px-2 py-1 text-right font-mono text-[12px]", r.stats.by_verdict.violation ? "text-bad" : "text-dim")}>{r.stats.by_verdict.violation ?? 0}</td>
                    <td className="px-2 py-1"><Bar value={((r.stats.by_verdict.pass ?? 0) / total) * 100} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Card>
    </div>
  );
}
