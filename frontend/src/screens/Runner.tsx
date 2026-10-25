import { Ban, Building2, EyeOff, Gauge, Lock, Play, ShieldCheck, Shuffle, TriangleAlert, UserX } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bar, Card, CardBody, CardHeader, IconTile } from "@/components/ui/card";
import { Field, Input, Switch, Toggle } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type ModuleInfo, type Run } from "@/lib/api";
import { fmtTime, MODULE_LABEL } from "@/lib/utils";
import { PageHeader, SectionTitle } from "./common";

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

  return (
    <div className="space-y-12">
      <PageHeader
        kicker={active ? "Running" : "Read-only by default"} kickerTone={active ? "warn" : "accent"}
        title="Test Runner"
        hint={<>Choose the checks, review the safety limits and run. <span className="font-semibold text-accent">{selected.length} modules</span> are
          selected; requests go only to <span className="font-mono text-ink">{project.target.allowed_hosts.join(", ")}</span>.</>}
        actions={active ? (
          <Button variant="danger" onClick={() => act(() => api.cancelRun(run!.id), "Cancelling after in-flight requests")}><Ban className="size-4" /> Cancel run</Button>
        ) : (
          <Button variant="accent" disabled={selected.length === 0} onClick={start}><Play className="size-4" /> Start run ({selected.length})</Button>
        )}
      />

      {missing.length > 0 && (
        <div className="flex items-center gap-3 rounded-2xl bg-warn/12 px-5 py-4 text-sm text-warn">
          <TriangleAlert className="size-4 shrink-0" /> No token for {missing.map((m) => m.name).join(", ")} - their checks will be skipped. Set tokens in Identity Manager.
        </div>
      )}

      {run && (
        <Card tone="inverse" className="p-7">
          <div className="absolute -right-16 -top-16 size-56 rounded-full bg-accent/25 blur-3xl" />
          <div className="relative flex flex-col gap-6 md:flex-row md:items-center md:justify-between">
            <div className="flex items-center gap-5">
              <IconTile className="size-14 bg-accent-solid text-white"><Gauge className="size-6" /></IconTile>
              <div>
                <div className="text-[11px] font-bold uppercase tracking-[0.16em] opacity-70">{run.status} - started {fmtTime(run.started_at)}</div>
                <h3 className="mt-1 font-display text-3xl font-bold tracking-tight">Run {run.id}</h3>
              </div>
            </div>
            {!active && <Button variant="accent" onClick={() => { setFocusRun(run.id); go("findings"); }}><ShieldCheck className="size-4" /> Open findings</Button>}
          </div>
          <div className="relative mt-6">
            <div className="h-2 w-full overflow-hidden bg-white/10"><div className="h-full bg-[#3fbf75] transition-all" style={{ width: `${pct}%` }} /></div>
            <div className="mt-4 flex flex-wrap gap-x-7 gap-y-2 text-sm">
              <span className="font-semibold">{run.stats.done}/{run.stats.total} checks ({pct}%)</span>
              <span className="opacity-70">{run.stats.requests} requests{run.stats.retries ? ` · ${run.stats.retries} retries (${run.stats.backoff_s}s back-off)` : ""}</span>
              <span className="font-semibold text-[#f2716b]">{v.violation ?? 0} violations</span>
              <span className="font-semibold text-[#f59a3c]">{v.needs_review ?? 0} review</span>
              <span className="font-semibold text-[#3fbf75]">{v.pass ?? 0} passed</span>
              <span className="opacity-70">{v.inconclusive ?? 0} inconclusive</span>
              <span className="opacity-70">{v.skipped ?? 0} skipped</span>
            </div>
            {run.error && <p className="mt-3 text-sm text-[#f2716b]">{run.error}</p>}
            {(run.extra.warnings ?? []).map((w) => <p key={w} className="mt-2 text-xs text-[#f59a3c]">{w}</p>)}
          </div>
        </Card>
      )}

      <section className="space-y-6">
        <SectionTitle title="Modules" hint="Each module records what passed, not only what failed." />
        <div className="grid gap-5 md:grid-cols-2">
          {mods?.modules.map((m) => {
            const Icon = ICONS[m.name] ?? ShieldCheck;
            const on = selected.includes(m.name);
            return (
              <div key={m.name} className={on
                ? "flex flex-col justify-between gap-6 rounded-3xl bg-panel p-7 shadow-[0_24px_40px_-16px_rgb(11_28_48/0.10)] ring-1 ring-line/60 transition-colors dark:shadow-none"
                : "flex flex-col justify-between gap-6 rounded-3xl bg-panel2 p-7 transition-colors"}>
                <div className="flex items-start justify-between gap-4">
                  <IconTile tone={on ? "accent" : "info"}><Icon className="size-5" /></IconTile>
                  <Switch checked={on} label={m.title}
                    onChange={(c) => setSelected(c ? [...selected, m.name] : selected.filter((x) => x !== m.name))} />
                </div>
                <div>
                  <h3 className="font-display text-xl font-bold tracking-tight">{m.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-mute">{m.description}</p>
                </div>
              </div>
            );
          })}
          {mods?.roadmap.map((m) => (
            <div key={m.name} className="flex items-center justify-between rounded-3xl border border-dashed border-line px-7 py-5 text-mute">
              <span className="font-display font-semibold">{m.title}</span><Badge>planned</Badge>
            </div>
          ))}
        </div>
      </section>

      <section className="grid gap-6 lg:grid-cols-5">
        <Card className="lg:col-span-2">
          <CardHeader title="Safety limits" hint="Requests go only to allowed hosts, one validated address per request. Redirects are not followed." />
          <CardBody className="space-y-5">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Requests / second"><Input type="number" min={0.1} max={100} step={0.5} value={limits.rps} onChange={(e) => setLimits({ ...limits, rps: Number(e.target.value) })} /></Field>
              <Field label="Budget per run"><Input type="number" min={1} value={limits.budget} onChange={(e) => setLimits({ ...limits, budget: Number(e.target.value) })} /></Field>
            </div>
            <div className="rounded-2xl bg-panel2 p-4">
              <Toggle checked={limits.mutating} onChange={(x) => setLimits({ ...limits, mutating: x })} label={<span className="font-semibold">Allow state-changing requests</span>} />
              <p className="mt-2 text-xs text-mute">PUT / POST / DELETE. Off by default; use only with disposable test data and a reset endpoint.</p>
              {limits.mutating && (
                <div className="mt-4 space-y-3">
                  <Field label="Reset endpoint (POST)" hint="Called after every state-changing request"><Input className="font-mono" value={limits.resetPath} onChange={(e) => setLimits({ ...limits, resetPath: e.target.value })} placeholder="/__test/reset" /></Field>
                  <Field label="Reset as identity"><Input value={limits.resetIdentity} onChange={(e) => setLimits({ ...limits, resetIdentity: e.target.value })} placeholder="admin" /></Field>
                  {!limits.resetPath && <Toggle checked={limits.noReset} onChange={(x) => setLimits({ ...limits, noReset: x })} label="I accept that test data is not reset" />}
                </div>
              )}
            </div>
          </CardBody>
        </Card>

        <div className="space-y-5 lg:col-span-3">
          <SectionTitle title="Previous runs" />
          <div className="space-y-3">
            {history.length === 0 && <p className="rounded-3xl bg-panel2 p-6 text-sm text-mute">No runs yet.</p>}
            {history.map((r) => {
              const total = Object.values(r.stats.by_verdict).reduce((a, n) => a + n, 0) || 1;
              return (
                <button key={r.id} onClick={() => { setFocusRun(r.id); go("findings"); }}
                  className="block w-full cursor-pointer rounded-2xl bg-panel2 p-5 text-left transition-colors hover:bg-high">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <span className="font-mono text-xs font-semibold">{r.id}</span>
                      <span className="ml-3 text-xs text-mute">{fmtTime(r.started_at)}</span>
                    </div>
                    <Badge tone={r.status === "completed" ? "ok" : r.status === "failed" ? "bad" : "mute"}>{r.status}</Badge>
                  </div>
                  <div className="mt-2 text-xs text-mute">{r.modules.map((m) => MODULE_LABEL[m] ?? m).join(", ")}</div>
                  <div className="mt-3 flex items-center gap-4">
                    <Bar value={((r.stats.by_verdict.pass ?? 0) / total) * 100} />
                    <span className="shrink-0 text-xs font-bold text-bad">{r.stats.by_verdict.violation ?? 0} violations</span>
                  </div>
                </button>
              );
            })}
          </div>
        </div>
      </section>
    </div>
  );
}
