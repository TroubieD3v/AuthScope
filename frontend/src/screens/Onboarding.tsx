import { FileUp, FlaskConical, Rocket, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, IconTile } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/lib/theme";

export function Onboarding({ onCreated, onCancel, notify }: {
  onCreated: (id: string) => Promise<void>; onCancel?: () => void; notify: (m: string, k?: "ok" | "bad") => void;
}) {
  const [name, setName] = useState("My API");
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:8000");
  const [hosts, setHosts] = useState("");
  const [yaml, setYaml] = useState("");
  const [busy, setBusy] = useState(false);
  const [demoUrl, setDemoUrl] = useState("http://127.0.0.1:8000");
  useEffect(() => { fetch("/api/health").then((r) => r.json()).then((h) => h.demo_url && setDemoUrl(h.demo_url)).catch(() => undefined); }, []);

  const run = async (fn: () => Promise<{ id: string }>) => {
    setBusy(true);
    try { await onCreated((await fn()).id); } catch (e) { notify(e instanceof Error ? e.message : String(e), "bad"); }
    setBusy(false);
  };

  return (
    <div className="min-h-full">
      <header className="sticky top-0 z-40 border-b border-line/60 bg-bg/75 backdrop-blur-xl">
        <div className="mx-auto flex h-[68px] max-w-5xl items-center justify-between px-6">
          <Logo />
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto max-w-5xl space-y-12 px-6 py-12">
        <section className="max-w-2xl">
          <Badge tone="accent" className="mb-4">API authorization testing</Badge>
          <h1 className="font-display text-5xl font-semibold leading-[1.02] tracking-[-0.035em] md:text-6xl">
            Who can <span className="text-accent">really</span> reach what?
          </h1>
          <p className="mt-5 text-[15px] leading-relaxed text-mute">
            AuthScope finds BOLA/IDOR, BFLA and BOPLA by comparing what your API actually returns with the access policy
            you expect, and hands you reproducible evidence for every violation.
          </p>
        </section>

        <div className="grid gap-6 lg:grid-cols-12">
          <Card tone="inverse" className="p-8 lg:col-span-7">
            <div className="absolute -right-16 -top-16 size-60 rounded-full bg-accent/25 blur-3xl" />
            <div className="relative flex items-start gap-5">
              <IconTile className="size-14 bg-accent-solid text-white"><Rocket className="size-6" /></IconTile>
              <div>
                <h2 className="font-display text-3xl font-bold tracking-tight">Try the demo API</h2>
                <p className="mt-1 text-sm opacity-75">Intentionally vulnerable. Start it with <code className="font-mono">python -m demo_api</code>.</p>
              </div>
            </div>
            <div className="relative mt-8 flex flex-col gap-3 sm:flex-row sm:items-end">
              <label className="block flex-1">
                <span className="mb-1.5 block text-[11px] font-semibold uppercase tracking-[0.12em] opacity-70">Demo API address</span>
                <input value={demoUrl} onChange={(e) => setDemoUrl(e.target.value)}
                  className="h-10 w-full rounded-[3px] border border-white/15 bg-white/10 px-3 font-mono text-sm text-on-inverse focus:border-[#3fbf75] focus:outline-none" />
              </label>
              <Button variant="accent" disabled={busy} onClick={() => run(() => api.createDemo(demoUrl))}><Rocket className="size-4" /> Load demo project</Button>
            </div>
          </Card>

          <div className="space-y-4 lg:col-span-5">
            {[
              ["Read-only by default", "Writes need an explicit switch and a reset endpoint."],
              ["Explicit host allow-list", "One validated address per request; nothing else is contacted."],
              ["Secrets stay out", "Tokens never reach the config, the database or reports."],
            ].map(([t, d]) => (
              <div key={t} className="flex items-start gap-4 rounded-2xl bg-panel2 p-5">
                <IconTile className="size-10"><ShieldCheck className="size-4" /></IconTile>
                <div><div className="font-display font-bold">{t}</div><div className="mt-0.5 text-sm text-mute">{d}</div></div>
              </div>
            ))}
          </div>
        </div>

        <div className="grid gap-6 lg:grid-cols-2">
          <Card>
            <CardHeader title="Connect your API" hint="Test only systems you are authorized to test. Requests go only to the hosts you list." />
            <CardBody className="grid grid-cols-2 gap-4">
              <Field label="Project name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
              <Field label="Base URL"><Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8000" /></Field>
              <Field label="Allowed hosts" hint="Comma separated. Required unless the target is localhost." className="col-span-2">
                <Input value={hosts} onChange={(e) => setHosts(e.target.value)} placeholder="api.staging.example.com" />
              </Field>
              <div className="col-span-2">
                <Button disabled={busy} onClick={() => run(() => api.createProject({
                  name, target: { base_url: baseUrl, allowed_hosts: hosts.split(",").map((h) => h.trim()).filter(Boolean) },
                }))}><FlaskConical className="size-4" /> Create project</Button>
              </div>
            </CardBody>
          </Card>

          <Card>
            <CardHeader title="Import an existing config" hint="authscope.yaml - secrets are never part of it; tokens come from env vars or the UI." />
            <CardBody className="space-y-3">
              <Textarea rows={5} value={yaml} onChange={(e) => setYaml(e.target.value)} placeholder={"target:\n  base_url: http://127.0.0.1:8000\nidentities: [alice, bob, admin]"} />
              <div className="flex gap-2">
                <label className="inline-flex h-10 cursor-pointer items-center gap-2 rounded-[3px] bg-panel2 px-4 text-sm font-semibold hover:bg-high">
                  <FileUp className="size-4" /> Choose file
                  <input type="file" accept=".yaml,.yml" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setYaml(await f.text()); }} />
                </label>
                <Button variant="outline" disabled={busy || !yaml.trim()} onClick={() => run(() => api.importYaml(yaml))}>Import</Button>
              </div>
            </CardBody>
          </Card>
        </div>
        {onCancel && <div className="text-center"><Button variant="ghost" onClick={onCancel}>Back to current project</Button></div>}
      </main>
    </div>
  );
}
