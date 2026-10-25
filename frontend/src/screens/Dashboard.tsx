import { ArrowUpRight, Building2, EyeOff, Lock, Play, ShieldCheck, Shuffle, UserX } from "lucide-react";
import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Bar, Card, IconTile, Stat } from "@/components/ui/card";
import { useApp } from "@/ctx";
import { api, type CheckResult, type Dashboard as Dash } from "@/lib/api";
import { fmtTime, MODULE_LABEL, SEVERITY_TONE } from "@/lib/utils";
import { Dial, PageHeader, SectionTitle } from "./common";

const MODULE_ICON: Record<string, typeof Lock> = {
  bola: Shuffle, bfla: Lock, bopla: EyeOff, unauth: UserX, tenant: Building2, custom: ShieldCheck,
};

export function Dashboard() {
  const { project, go, setFocusRun } = useApp();
  const [d, setD] = useState<Dash | null>(null);
  const [top, setTop] = useState<CheckResult[]>([]);

  useEffect(() => {
    api.dashboard(project.id).then(async (dash) => {
      setD(dash);
      if (dash.latest_run) setTop((await api.results(dash.latest_run.id, "findings")).slice(0, 4));
    });
  }, [project.id]);

  if (!d) return <div className="text-mute">Loading...</div>;
  const v = d.verdicts;
  const violations = v.violation ?? 0;
  const review = v.needs_review ?? 0;
  const findings = violations + review;
  const tested = Object.entries(v).filter(([k]) => k !== "skipped").reduce((a, [, n]) => a + n, 0);
  const passed = v.pass ?? 0;
  const run = d.latest_run;
  const openRun = (id: string) => { setFocusRun(id); go("findings"); };

  return (
    <div className="space-y-12">
      <PageHeader
        kicker={!run ? "No runs yet" : violations ? "Action needed" : "Policy holds"}
        kickerTone={!run ? "mute" : violations ? "bad" : "accent"}
        title="Authorization posture"
        hint={run
          ? <>The last run checked <b className="text-ink">{tested} cases</b> across {d.endpoints} endpoints.{" "}
              {violations ? <><span className="font-semibold text-bad">{violations} break your policy</span>{review ? `, ${review} need review.` : "."}</> : "Nothing breaks your policy."}</>
          : "Add identities and objects, review the Permission Matrix, then start a run."}
        actions={<Button variant="accent" onClick={() => go("runner")}><Play className="size-4" /> New test run</Button>}
      />

      <section className="grid gap-6 lg:grid-cols-5">
        <Card tone="container" className="flex flex-col items-center px-6 py-10 lg:col-span-3">
          <Dial outer={tested ? passed / tested : 0} inner={tested ? findings / tested : 0}>
            <div className="font-display text-6xl font-bold tracking-tight">{run ? findings : "-"}</div>
            <div className="mt-1 text-[11px] font-bold uppercase tracking-[0.2em] text-mute">Findings</div>
            <div className="mt-4 flex items-center justify-center gap-2 font-display text-lg font-semibold text-accent">
              <ShieldCheck className="size-4" /> {run ? `${passed} passed` : "not run"}
            </div>
          </Dial>
          <div className="mt-8 grid w-full max-w-md grid-cols-2 gap-8">
            <div>
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-mute">Policy violations</div>
              <div className="mt-1 font-display text-3xl font-bold text-bad">{run ? violations : "-"}</div>
            </div>
            <div className="text-right">
              <div className="text-[11px] font-bold uppercase tracking-[0.14em] text-mute">Needs review</div>
              <div className="mt-1 font-display text-3xl font-bold text-warn">{run ? review : "-"}</div>
            </div>
          </div>
        </Card>

        <div className="flex flex-col gap-6 lg:col-span-2">
          <div className="grid grid-cols-2 gap-4">
            <Stat label="Endpoints" value={d.endpoints} />
            <Stat label="Test identities" value={d.identities} />
            <Stat label="Test objects" value={d.resources} />
            <Stat label="Checks passed" value={run ? passed : "-"} tone={run ? "ok" : undefined} />
          </div>
          <Card tone="inverse" className="flex flex-1 flex-col justify-between gap-6 p-7">
            <div className="absolute -right-10 -top-10 size-40 rounded-full bg-accent/25 blur-3xl" />
            <div className="relative flex items-start gap-4">
              <IconTile tone="accent" className="bg-accent-solid text-white"><Play className="size-5" /></IconTile>
              <div>
                <h3 className="font-display text-2xl font-bold tracking-tight">Run every check</h3>
                <p className="mt-1 text-sm opacity-75">BOLA, BFLA, BOPLA, unauthenticated and cross-tenant, read-only and rate-limited.</p>
              </div>
            </div>
            <div className="relative flex items-center justify-between">
              <span className="text-xs opacity-70">{run ? `Last run ${fmtTime(run.started_at)}` : "No runs yet"}</span>
              <Button variant="accent" size="sm" onClick={() => go("runner")}>Configure run</Button>
            </div>
          </Card>
        </div>
      </section>

      {run && (
        <section className="space-y-6">
          <SectionTitle title="Results by module" hint={`Run ${run.id} - ${fmtTime(run.started_at)}`} />
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(d.modules).map(([m, c]) => {
              const Icon = MODULE_ICON[m] ?? ShieldCheck;
              const total = Object.entries(c).filter(([k]) => k !== "skipped").reduce((a, [, n]) => a + n, 0) || 1;
              const bad = c.violation ?? 0;
              return (
                <div key={m} className="flex flex-col justify-between rounded-3xl bg-panel2 p-6 transition-colors hover:bg-high">
                  <div className="flex items-start justify-between">
                    <IconTile tone={bad ? "bad" : "accent"}><Icon className="size-5" /></IconTile>
                    <span className={bad ? "text-xs font-bold text-bad" : "text-xs font-bold text-accent"}>
                      {bad ? `${bad} violation${bad > 1 ? "s" : ""}` : "Clean"}
                    </span>
                  </div>
                  <div className="mt-8">
                    <h4 className="font-display text-lg font-bold">{MODULE_LABEL[m] ?? m}</h4>
                    <div className="mt-1 flex items-baseline gap-2">
                      <span className="font-display text-3xl font-bold">{c.pass ?? 0}</span>
                      <span className="text-sm text-mute">of {total} passed</span>
                    </div>
                    <Bar className="mt-4" value={((c.pass ?? 0) / total) * 100} tone={bad ? "ink" : "accent"} />
                  </div>
                </div>
              );
            })}
          </div>
        </section>
      )}

      <section className="grid gap-6 lg:grid-cols-5">
        <div className="space-y-5 lg:col-span-3">
          <SectionTitle title="Top findings" actions={run && <button onClick={() => openRun(run.id)} className="cursor-pointer text-sm font-semibold text-accent hover:underline">View all</button>} />
          <div className="space-y-3">
            {!run && <p className="rounded-3xl bg-panel2 p-6 text-sm text-mute">Findings appear here after the first run.</p>}
            {run && top.length === 0 && <p className="rounded-3xl bg-panel2 p-6 text-sm text-accent">No violations in the latest run.</p>}
            {top.map((f) => (
              <button key={f.id} onClick={() => openRun(run!.id)} className="flex w-full cursor-pointer items-center gap-4 rounded-2xl bg-panel2 p-4 text-left transition-colors hover:bg-high">
                <IconTile tone={f.verdict === "violation" ? "bad" : "warn"} className="size-10"><ShieldCheck className="size-4" /></IconTile>
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-semibold">{f.name}</div>
                  <div className="mt-0.5 text-xs text-mute">{MODULE_LABEL[f.module] ?? f.module}</div>
                </div>
                <Badge tone={SEVERITY_TONE[f.severity]}>{f.severity}</Badge>
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-5 lg:col-span-2">
          <SectionTitle title="Run history" />
          <Card className="divide-y divide-line/70">
            {d.history.length === 0 && <p className="p-6 text-sm text-mute">Nothing yet.</p>}
            {d.history.map((r) => (
              <button key={r.id} onClick={() => openRun(r.id)} className="flex w-full cursor-pointer items-center justify-between gap-3 px-6 py-4 text-left transition-colors hover:bg-panel2">
                <div>
                  <div className="font-mono text-xs font-semibold">{r.id}</div>
                  <div className="mt-0.5 text-xs text-mute">{fmtTime(r.started_at)}</div>
                </div>
                <div className="flex items-center gap-3 text-xs font-bold">
                  <span className="text-bad">{r.violations}</span>
                  <span className="text-warn">{r.review}</span>
                  <span className="text-accent">{r.passed}</span>
                  <ArrowUpRight className="size-4 text-mute" />
                </div>
              </button>
            ))}
          </Card>
        </div>
      </section>
    </div>
  );
}
