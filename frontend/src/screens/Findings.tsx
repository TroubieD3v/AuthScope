import { Copy, Download, GitCompare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader } from "@/components/ui/card";
import { Select } from "@/components/ui/field";
import { useApp } from "@/ctx";
import { api, type CheckResult, type Exchange } from "@/lib/api";
import { cn, copy, fmtTime, MODULE_LABEL, VERDICT_META } from "@/lib/utils";
import type { Run } from "@/lib/api";
import { PageHeader, SevMark, VerdictBadge } from "./common";

type Tab = "findings" | "passed" | "other";
const SEV_ORDER = ["critical", "high", "medium", "low", "info"];

export function Findings() {
  const { project, focusRun, notify } = useApp();
  const [runs, setRuns] = useState<Run[]>([]);
  const [rid, setRid] = useState<string | null>(focusRun);
  const [all, setAll] = useState<CheckResult[]>([]);
  const [detail, setDetail] = useState<Record<string, CheckResult>>({});
  const [tab, setTab] = useState<Tab>("findings");
  const [module, setModule] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const [diff, setDiff] = useState<{ new: CheckResult[]; fixed: CheckResult[]; unchanged: CheckResult[] } | null>(null);

  useEffect(() => {
    api.runs(project.id).then((rs) => {
      const done = rs.filter((r) => r.status !== "queued" && r.status !== "running");
      setRuns(done);
      setRid((cur) => cur ?? done[0]?.id ?? null);
    });
  }, [project.id]);

  useEffect(() => {
    setDiff(null); setOpen(null);
    if (!rid) { setAll([]); return; }
    Promise.all([api.results(rid, "all"), api.results(rid, "findings")]).then(([light, full]) => {
      setAll(light);
      setDetail(Object.fromEntries(full.map((f) => [f.id, f])));
    });
  }, [rid]);

  const view = useMemo(() => {
    const byTab = all.filter((r) =>
      tab === "findings" ? r.verdict === "violation" || r.verdict === "needs_review"
        : tab === "passed" ? r.verdict === "pass" : ["inconclusive", "skipped", "error"].includes(r.verdict));
    return byTab.filter((r) => !module || r.module === module).sort((a, b) =>
      (a.verdict === b.verdict ? 0 : a.verdict === "violation" ? -1 : b.verdict === "violation" ? 1 : 0) ||
      SEV_ORDER.indexOf(a.severity) - SEV_ORDER.indexOf(b.severity));
  }, [all, tab, module]);

  const counts = {
    findings: all.filter((r) => r.verdict === "violation" || r.verdict === "needs_review").length,
    passed: all.filter((r) => r.verdict === "pass").length,
    other: all.filter((r) => ["inconclusive", "skipped", "error"].includes(r.verdict)).length,
  };
  const idx = runs.findIndex((r) => r.id === rid);
  const previous = idx >= 0 ? runs[idx + 1] : undefined;

  const select = async (r: CheckResult) => {
    setOpen(r.id);
    if (!detail[r.id] && rid) {
      try { const full = await api.result(rid, r.id); setDetail((d) => ({ ...d, [r.id]: full })); } catch (e) { notify(String(e), "bad"); }
    }
  };
  const selected = open ? (detail[open] ?? all.find((r) => r.id === open)) : undefined;

  return (
    <div className="space-y-3">
      <PageHeader kicker={counts.findings ? `${counts.findings} to fix or review` : "Evidence"} kickerTone={counts.findings ? "bad" : "mute"} title="Findings & Reports"
        hint="Each result keeps both requests, the response differences, the expected policy and a curl to reproduce it. Tokens are masked."
        actions={rid && (
          <>
            <span className="mr-1 text-xs text-mute">Export</span>
            {(["html", "md", "json", "pytest"] as const).map((f) => (
              <a key={f} href={api.reportUrl(rid, f)}>
                <Button size="sm" variant="secondary"><Download className="size-3.5" /> {f === "md" ? "Markdown" : f === "pytest" ? "pytest" : f.toUpperCase()}</Button>
              </a>
            ))}
          </>
        )} />

      {/* Filter bar */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="text-mute">Run</span>
        <Select className="h-7 w-72 text-xs" value={rid ?? ""} onChange={(e) => setRid(e.target.value)}>
          {runs.length === 0 && <option value="">No finished runs</option>}
          {runs.map((r) => <option key={r.id} value={r.id}>{r.id} - {fmtTime(r.started_at)} - {r.stats.by_verdict.violation ?? 0} violations</option>)}
        </Select>
        <span className="ml-2 text-mute">Module</span>
        <Select className="h-7 w-44 text-xs" value={module} onChange={(e) => setModule(e.target.value)}>
          <option value="">All modules</option>
          {[...new Set(all.map((r) => r.module))].map((m) => <option key={m} value={m}>{MODULE_LABEL[m] ?? m}</option>)}
        </Select>
        {rid && previous && (
          <Button size="sm" variant="secondary" onClick={() => api.diff(rid, previous.id).then(setDiff)}>
            <GitCompare className="size-3.5" /> Compare with {previous.id}
          </Button>
        )}
        <div className="ml-auto flex border border-line">
          {(["findings", "passed", "other"] as Tab[]).map((t) => (
            <button key={t} onClick={() => { setTab(t); setOpen(null); }}
              className={cn("cursor-pointer border-r border-line px-2.5 py-1 last:border-r-0", tab === t ? "bg-panel text-ink" : "text-mute hover:text-ink")}>
              {t === "findings" ? "Findings" : t === "passed" ? "Passed" : "Inconclusive / skipped"} <span className="font-mono">{counts[t]}</span>
            </button>
          ))}
        </div>
      </div>

      {diff && (
        <Card>
          <CardHeader title="Regression: compared with previous run" actions={<Button size="sm" variant="ghost" onClick={() => setDiff(null)}>Close</Button>} />
          <div className="grid grid-cols-3 divide-x divide-line text-xs">
            {([["New", diff.new, "text-bad"], ["Fixed", diff.fixed, "text-ok"], ["Unchanged", diff.unchanged, "text-mute"]] as const).map(([t, list, cls]) => (
              <div key={t} className="p-3">
                <div className="flex items-baseline gap-2"><span className={`font-mono text-lg ${cls}`}>{list.length}</span><span className="text-mute">{t}</span></div>
                <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto">{list.map((r) => <li key={r.id} className="truncate font-mono text-[11.5px]" title={r.name}>{r.name}</li>)}</ul>
              </div>
            ))}
          </div>
        </Card>
      )}

      <div className={cn("grid gap-3", selected && "xl:grid-cols-[minmax(0,1fr)_340px]")}>
        <div className="min-w-0 space-y-3">
          {/* Results table */}
          <Card className="max-h-[330px] overflow-auto">
            {rid && view.length === 0 && <p className="px-3 py-6 text-center text-xs text-mute">{tab === "findings" ? "No violations - everything matches the policy." : "Nothing here."}</p>}
            {!rid && <p className="px-3 py-6 text-center text-xs text-mute">Run a test first.</p>}
            {view.length > 0 && (
              <table className="w-full border-collapse text-[12.5px]">
                <thead className="sticky top-0 z-10 bg-panel2 text-left text-xs text-mute">
                  <tr>
                    {["#", "Severity", "Verdict", "Module", "Identity", "Check", "Expected", "Observed"].map((h) => (
                      <th key={h} className={cn("whitespace-nowrap border-b border-line bg-panel2 px-2 py-1.5 font-medium", h === "#" && "w-10 text-right")}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {view.map((r, i) => {
                    const on = open === r.id;
                    return (
                      <tr key={r.id} onClick={() => select(r)}
                        className={cn("cursor-pointer border-b border-line2", on ? "bg-sel" : "hover:bg-panel2/70", r.verdict === "pass" && !on && "text-mute")}>
                        <td className="px-2 py-1 text-right font-mono text-[11.5px] text-dim">{i + 1}</td>
                        <td className="whitespace-nowrap px-2 py-1"><SevMark s={r.severity} />{r.severity}</td>
                        <td className={cn("whitespace-nowrap px-2 py-1", VERDICT_META[r.verdict].tone === "bad" && "text-bad", VERDICT_META[r.verdict].tone === "warn" && "text-warn")}>{VERDICT_META[r.verdict].label}</td>
                        <td className="whitespace-nowrap px-2 py-1">{MODULE_LABEL[r.module] ?? r.module}</td>
                        <td className="whitespace-nowrap px-2 py-1">{r.identity ?? "anonymous"}</td>
                        <td className="max-w-0 w-full px-2 py-1">
                          <button className="block w-full cursor-pointer truncate text-left font-mono text-[12px]" title={r.name}>{r.name}</button>
                        </td>
                        <td className="whitespace-nowrap px-2 py-1 text-mute">{r.expected ?? "-"}</td>
                        <td className="whitespace-nowrap px-2 py-1 font-mono text-[11.5px]">{r.observed}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            )}
          </Card>

          {selected && <Editors r={selected} />}
        </div>

        {selected && <Inspector r={selected} />}
      </div>
    </div>
  );
}

/** Baseline and test side by side, each with request / response tabs. */
function Editors({ r }: { r: CheckResult }) {
  const ev = r.evidence;
  if (!ev || (!ev.baseline && !ev.test)) {
    return <Card><p className="px-3 py-4 text-xs text-mute">No request evidence for this result (it was {r.verdict}).</p></Card>;
  }
  // BOPLA names the exact fields that must not be returned; mark those lines in the test response.
  const leaked = (ev.diff.find((d) => d.startsWith("Restricted fields present:")) ?? "").replace("Restricted fields present:", "").split(",").map((s) => s.trim()).filter(Boolean);
  return (
    <div className={cn("grid gap-3", ev.baseline && ev.test ? "lg:grid-cols-2" : "")}>
      {ev.baseline && <Editor title="Baseline" ex={ev.baseline} initial="request" />}
      {ev.test && <Editor title="Test" ex={ev.test} initial="response" mark={r.verdict === "violation" ? leaked : []} />}
    </div>
  );
}

function Editor({ title, ex, initial, mark = [] }: { title: string; ex: Exchange; initial: "request" | "response"; mark?: string[] }) {
  const [tab, setTab] = useState<"request" | "response">(initial);
  const lines = tab === "request" ? requestLines(ex) : responseLines(ex);
  const statusCls = ex.status === null || ex.status >= 500 ? "text-bad" : ex.status < 300 ? "text-ink" : "text-mute";
  return (
    <Card className="flex min-w-0 flex-col">
      <div className="flex items-center gap-3 border-b border-line bg-panel2/60 px-3 text-xs">
        <span className="py-1.5 font-semibold text-[12.5px]">{title}</span>
        <span className="text-mute">{ex.identity ?? "anonymous"}</span>
        {(["request", "response"] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={cn("cursor-pointer py-1.5 capitalize", tab === t ? "text-ink shadow-[inset_0_-2px_0_var(--accent)]" : "text-mute hover:text-ink")}>{t}</button>
        ))}
        <span className={cn("ml-auto font-mono text-[11.5px]", statusCls)}>{ex.status ?? "ERR"} · {ex.elapsed_ms} ms</span>
      </div>
      <pre className="max-h-[300px] overflow-auto py-1.5 text-[12px] leading-[1.6]">
        {lines.map((l, i) => {
          const hit = mark.some((f) => l.includes(`"${f}"`));
          return (
            <div key={i} className={cn("flex", hit && "bg-bad/12 shadow-[inset_2px_0_0_var(--bad)]")}>
              <span className="w-10 shrink-0 select-none pr-3 text-right text-dim">{i + 1}</span>
              <span className="whitespace-pre-wrap break-all pr-3"><Syntax line={l} /></span>
            </div>
          );
        })}
      </pre>
    </Card>
  );
}

function requestLines(ex: Exchange): string[] {
  const out = [`${ex.method} ${ex.url}`, ...Object.entries(ex.request_headers).map(([k, v]) => `${k}: ${v}`)];
  if (ex.request_body) out.push("", ...pretty(ex.request_body));
  return out;
}

function responseLines(ex: Exchange): string[] {
  if (ex.error) return [ex.error];
  const out = [`HTTP ${ex.status}`, ...Object.entries(ex.response_headers ?? {}).map(([k, v]) => `${k}: ${v}`)];
  out.push("", ...(ex.response_body ? pretty(ex.response_body) : ["(empty body)"]));
  return out;
}

function pretty(body: string): string[] {
  try { return JSON.stringify(JSON.parse(body), null, 2).split("\n"); } catch { return body.split("\n"); }
}

/** Minimal highlighting: header names, JSON keys, strings and numbers. */
function Syntax({ line }: { line: string }) {
  const header = /^([A-Za-z0-9-]+): (.*)$/.exec(line);
  if (header && !line.startsWith(" ") && !line.startsWith("{")) {
    return <><span className="text-accent">{header[1]}</span>: {header[2]}</>;
  }
  const json = /^(\s*)"([^"]+)": (.*?)(,?)$/.exec(line);
  if (json) {
    const v = json[3];
    const cls = v.startsWith('"') ? "text-syn-str" : /^-?\d/.test(v) ? "text-syn-num" : "text-ink";
    return <>{json[1]}<span className="text-syn-key">"{json[2]}"</span>: <span className={cls}>{v}</span>{json[4]}</>;
  }
  return <>{line}</>;
}

/** Inspector: verdict, the rule behind it, the analysis and a reproduction. */
function Inspector({ r }: { r: CheckResult }) {
  const ev = r.evidence;
  return (
    <Card className="self-start">
      <div className="flex items-center justify-between border-b border-line bg-panel2/60 px-3 py-1.5">
        <span className="text-[12.5px] font-semibold">Inspector</span>
        <span className="text-xs text-mute">{MODULE_LABEL[r.module] ?? r.module}</span>
      </div>
      <div className="space-y-1.5 border-b border-line2 px-3 py-2.5">
        <div className="flex flex-wrap gap-1"><VerdictBadge v={r.verdict} />{r.verdict !== "pass" && r.verdict !== "skipped" && <Badge>{r.severity}</Badge>}</div>
        <div className="font-mono text-[12px] leading-snug">{r.name}</div>
        <p className="text-xs text-mute">{r.message}</p>
      </div>
      <Section label="Expected policy"><p className="text-[12.5px]">{ev?.expected || "-"}</p></Section>
      {ev && ev.diff.length > 0 && (
        <Section label="Analysis">
          <ul className="space-y-0.5 text-[12px]">{ev.diff.map((d) => <li key={d} className="break-words">{d}</li>)}</ul>
        </Section>
      )}
      {ev && ev.reproduction.length > 0 && (
        <Section label="Reproduce" action={<Button size="sm" variant="ghost" onClick={() => copy(ev.reproduction.join("\n\n"))}><Copy className="size-3" /> Copy</Button>}>
          <p className="mb-1 text-[11px] text-dim">Tokens come from env variables.</p>
          <pre className="overflow-x-auto whitespace-pre-wrap break-all border border-line bg-bg p-2 text-[11.5px] leading-relaxed">{ev.reproduction.join("\n\n")}</pre>
        </Section>
      )}
    </Card>
  );
}

function Section({ label, action, children }: { label: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="border-b border-line2 px-3 py-2.5 last:border-b-0">
      <div className="mb-1 flex items-center justify-between">
        <span className="text-[11px] text-mute">{label}</span>
        {action}
      </div>
      {children}
    </div>
  );
}
