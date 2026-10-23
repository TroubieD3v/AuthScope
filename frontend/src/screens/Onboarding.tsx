import { FileUp, FlaskConical, Rocket, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";

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
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center gap-6 px-6 py-12">
      <div className="flex items-center gap-3">
        <div className="grid size-11 place-items-center rounded-xl bg-accent/15 ring-1 ring-accent/40"><ShieldAlert className="size-5 text-accent" /></div>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AuthScope</h1>
          <p className="text-sm text-mute">Finds BOLA/IDOR, BFLA and BOPLA by comparing real API behaviour with your access policy.</p>
        </div>
      </div>

      <Card className="border-accent/30">
        <CardHeader title="Try it on the bundled demo API" hint="Intentionally vulnerable. Start it with: python -m demo_api (port 8000)" />
        <CardBody className="flex items-end gap-3">
          <Field label="Demo API address" className="flex-1"><Input value={demoUrl} onChange={(e) => setDemoUrl(e.target.value)} /></Field>
          <Button disabled={busy} onClick={() => run(() => api.createDemo(demoUrl))}><Rocket className="size-4" /> Load demo project</Button>
        </CardBody>
      </Card>

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
        <CardHeader title="Import an existing config" hint="authscope.yaml (secrets are never part of it - tokens come from env vars or the UI)" />
        <CardBody className="space-y-3">
          <Textarea rows={5} value={yaml} onChange={(e) => setYaml(e.target.value)} placeholder="target:&#10;  base_url: http://127.0.0.1:8000&#10;identities: [alice, bob, admin]" />
          <div className="flex gap-2">
            <label className="inline-flex h-9 cursor-pointer items-center gap-2 rounded-md border border-line bg-panel2 px-4 text-sm hover:bg-[#1b2735]">
              <FileUp className="size-4" /> Choose file
              <input type="file" accept=".yaml,.yml" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setYaml(await f.text()); }} />
            </label>
            <Button variant="secondary" disabled={busy || !yaml.trim()} onClick={() => run(() => api.importYaml(yaml))}>Import</Button>
          </div>
        </CardBody>
      </Card>
      {onCancel && <Button variant="ghost" className="self-center" onClick={onCancel}>Back to current project</Button>}
    </div>
  );
}
