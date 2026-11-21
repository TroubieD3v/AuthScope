import { FileUp, FlaskConical, Rocket } from "lucide-react";
import { useEffect, useState } from "react";
import { Logo } from "@/components/logo";
import { Button } from "@/components/ui/button";
import { Field, Input, Textarea } from "@/components/ui/field";
import { api } from "@/lib/api";
import { ThemeToggle } from "@/lib/theme";
import { cn } from "@/lib/utils";

type Mode = "demo" | "connect" | "import";

/** Start window: pick how to open a project, like the project dialog of a desktop scanner. */
export function Onboarding({ onCreated, onCancel, notify }: {
  onCreated: (id: string) => Promise<void>; onCancel?: () => void; notify: (m: string, k?: "ok" | "bad") => void;
}) {
  const [mode, setMode] = useState<Mode>("demo");
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

  const options: { id: Mode; title: string; hint: string }[] = [
    { id: "demo", title: "Demo project", hint: "Intentionally vulnerable API with users, orders and an admin area" },
    { id: "connect", title: "Connect your API", hint: "Base URL and an explicit host allow-list" },
    { id: "import", title: "Import authscope.yaml", hint: "An existing config; secrets are never part of it" },
  ];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex h-9 items-center justify-between border-b border-line bg-chrome px-3">
        <Logo />
        <ThemeToggle />
      </header>

      <main className="flex flex-1 items-start justify-center px-4 py-14">
        <div className="w-full max-w-[860px] border border-line bg-panel">
          <div className="border-b border-line bg-panel2/60 px-4 py-2.5">
            <h1 className="text-[14px] font-semibold">Open a project</h1>
            <p className="text-xs text-mute">
              AuthScope finds BOLA/IDOR, BFLA and BOPLA by comparing what your API actually returns with the access policy
              you expect, and keeps reproducible evidence for every violation.
            </p>
          </div>

          <div className="grid md:grid-cols-[260px_minmax(0,1fr)]">
            <ul className="border-b border-line md:border-b-0 md:border-r">
              {options.map((o) => (
                <li key={o.id}>
                  <button onClick={() => setMode(o.id)}
                    className={cn("block w-full cursor-pointer border-b border-line2 px-4 py-2.5 text-left", mode === o.id ? "bg-sel" : "hover:bg-panel2/70")}>
                    <div className="text-[12.5px] font-medium">{o.title}</div>
                    <div className="text-xs text-mute">{o.hint}</div>
                  </button>
                </li>
              ))}
              <li className="space-y-1 px-4 py-3 text-xs text-mute">
                <div>Read-only by default</div>
                <div>One validated host per request</div>
                <div>Tokens never reach config, database or reports</div>
              </li>
            </ul>

            <div className="p-4">
              {mode === "demo" && (
                <div className="space-y-3">
                  <p className="text-[12.5px]">Start the demo API with <code className="bg-bg px-1 font-mono text-[12px]">python -m demo_api</code>, then load the project.</p>
                  <div className="flex items-end gap-2">
                    <label className="block flex-1">
                      <span className="mb-1 block text-xs text-mute">Demo API address</span>
                      <input value={demoUrl} onChange={(e) => setDemoUrl(e.target.value)}
                        className="h-8 w-full border border-line bg-bg px-2.5 font-mono text-[12.5px] text-ink focus:border-accent focus:outline-none" />
                    </label>
                    <Button disabled={busy} onClick={() => run(() => api.createDemo(demoUrl))}><Rocket className="size-3.5" /> Load demo project</Button>
                  </div>
                </div>
              )}

              {mode === "connect" && (
                <div className="grid grid-cols-2 gap-3">
                  <p className="col-span-2 text-xs text-mute">Test only systems you are authorized to test. Requests go only to the hosts you list.</p>
                  <Field label="Project name"><Input value={name} onChange={(e) => setName(e.target.value)} /></Field>
                  <Field label="Base URL"><Input className="font-mono" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="http://127.0.0.1:8000" /></Field>
                  <Field label="Allowed hosts" hint="Comma separated. Required unless the target is localhost." className="col-span-2">
                    <Input className="font-mono" value={hosts} onChange={(e) => setHosts(e.target.value)} placeholder="api.staging.example.com" />
                  </Field>
                  <div className="col-span-2">
                    <Button disabled={busy} onClick={() => run(() => api.createProject({
                      name, target: { base_url: baseUrl, allowed_hosts: hosts.split(",").map((h) => h.trim()).filter(Boolean) },
                    }))}><FlaskConical className="size-3.5" /> Create project</Button>
                  </div>
                </div>
              )}

              {mode === "import" && (
                <div className="space-y-2">
                  <p className="text-xs text-mute">Tokens come from environment variables or the UI, never from the file.</p>
                  <Textarea rows={8} value={yaml} onChange={(e) => setYaml(e.target.value)} placeholder={"target:\n  base_url: http://127.0.0.1:8000\nidentities: [alice, bob, admin]"} />
                  <div className="flex gap-2">
                    <label className="inline-flex h-8 cursor-pointer items-center gap-1.5 border border-line bg-panel px-3 text-[12.5px] font-medium hover:border-dim">
                      <FileUp className="size-3.5" /> Choose file
                      <input type="file" accept=".yaml,.yml" hidden onChange={async (e) => { const f = e.target.files?.[0]; if (f) setYaml(await f.text()); }} />
                    </label>
                    <Button variant="secondary" disabled={busy || !yaml.trim()} onClick={() => run(() => api.importYaml(yaml))}>Import</Button>
                  </div>
                </div>
              )}
            </div>
          </div>
          {onCancel && <div className="border-t border-line px-4 py-2 text-right"><Button variant="ghost" size="sm" onClick={onCancel}>Back to current project</Button></div>}
        </div>
      </main>
    </div>
  );
}
