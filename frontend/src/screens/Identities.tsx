import { KeyRound, Plus, Trash2, UserRound } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type Identity, type Resource } from "@/lib/api";
import { PageHeader, SectionTitle } from "./common";

const SOURCE_LABEL: Record<string, { text: string; tone: "ok" | "warn" | "mute" | "bad" }> = {
  runtime: { text: "token in memory", tone: "ok" },
  env: { text: "token from env", tone: "ok" },
  login: { text: "token via login flow", tone: "ok" },
  missing: { text: "no token", tone: "bad" },
  none: { text: "anonymous", tone: "mute" },
};

export function Identities() {
  const { project, reload } = useApp();
  const act = useAction();
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [ni, setNi] = useState({ name: "", role: "user", tenant: "", authType: "bearer", header: "X-API-Key", queryName: "api_key", username: "", loginPath: "", tokenPath: "access_token" });
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [nr, setNr] = useState({ type: "order", id: "", owner: "", tenant: "", parent: "", match: "" });
  const parseMatch = (txt: string) => Object.fromEntries(txt.split(";").map((p) => p.trim()).filter(Boolean)
    .map((p) => { const i = p.lastIndexOf("="); return [p.slice(0, i).trim(), p.slice(i + 1).trim()]; }));

  const addIdentity = () => act(async () => {
    const anon = ni.authType === "none";
    await api.putIdentity(project.id, {
      name: ni.name.trim(), role: anon ? "guest" : ni.role, tenant: ni.tenant || null,
      auth: {
        type: ni.authType as Identity["auth"]["type"], header_name: ni.header, cookie_name: "session",
        query_name: ni.queryName || "api_key", username: ni.authType === "basic" && ni.username ? ni.username : null,
      },
      login: !anon && ni.loginPath.trim()
        ? { method: "POST", path: ni.loginPath.trim(), body: { username: ni.name.trim(), password: "${password}" }, token_path: ni.tokenPath || "access_token" }
        : null,
    });
    setNi({ ...ni, name: "", loginPath: "" });
    await reload();
  }, "Identity added");

  const saveResources = (list: Resource[]) => act(async () => { await api.putResources(project.id, list); await reload(); });

  const owners = project.identities.filter((i) => i.auth.type !== "none");

  return (
    <div className="space-y-12">
      <PageHeader kicker="Test accounts" title="Identity Manager"
        hint={<>Who AuthScope acts as, and which objects belong to whom. Tokens are <span className="font-semibold text-ink">write-only</span>:
          kept in server memory for this session and never saved to the database, config or reports.</>} />

      <section className="space-y-6">
        <SectionTitle title="Test identities" hint="Or export the environment variable shown on a card before starting AuthScope." />
        <div className="grid gap-5 md:grid-cols-2">
          {project.identities.length === 0 && <p className="rounded-3xl bg-panel2 p-6 text-sm text-mute">Add at least two user identities and one admin.</p>}
          {project.identities.map((i) => {
            const src = SOURCE_LABEL[i.secret_source ?? "missing"];
            const anon = i.auth.type === "none";
            return (
              <div key={i.name} className="flex flex-col gap-5 rounded-3xl bg-panel2 p-6">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-4">
                    <div className={anon ? "grid size-12 place-items-center rounded-[3px] bg-high text-mute" : "grid size-12 place-items-center rounded-[3px] bg-primary font-display text-lg font-bold text-on-primary"}>
                      {anon ? <UserRound className="size-5" /> : i.name.slice(0, 1).toUpperCase()}
                    </div>
                    <div>
                      <div className="font-display text-xl font-bold tracking-tight">{i.name}</div>
                      <div className="mt-0.5 text-xs text-mute">
                        role <span className="font-mono text-ink">{i.role}</span>{i.tenant && <> · tenant <span className="font-mono text-ink">{i.tenant}</span></>}
                      </div>
                    </div>
                  </div>
                  <Button size="icon" variant="ghost" title="Remove identity" onClick={() => act(async () => { await api.deleteIdentity(project.id, i.name); await reload(); })}><Trash2 className="size-4" /></Button>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <Badge tone={src.tone}>{src.text}</Badge>
                  {!anon && <Badge tone="info">{i.auth.type}</Badge>}
                  {i.login && <Badge tone="accent">login flow</Badge>}
                </div>
                {!anon && (
                  <div className="space-y-2">
                    <div className="flex gap-2">
                      <Input type="password" autoComplete="off" className="font-mono"
                        placeholder={i.auth.type === "basic" ? (i.auth.username ? `password of ${i.auth.username}` : "user:password") : i.auth.type === "query" ? `?${i.auth.query_name}= value` : `${i.auth.type} token`}
                        value={tokens[i.name] ?? ""} onChange={(e) => setTokens({ ...tokens, [i.name]: e.target.value })} />
                      <Button variant="secondary" disabled={!tokens[i.name]} onClick={() => act(async () => {
                        await api.setSecret(project.id, i.name, tokens[i.name]); setTokens({ ...tokens, [i.name]: "" }); await reload();
                      }, `Token for ${i.name} stored in memory`)}><KeyRound className="size-4" /> Set</Button>
                    </div>
                    {i.login && (
                      <div className="flex gap-2">
                        <Input type="password" autoComplete="off" placeholder={i.password_source === "missing" ? "password for login" : "password set"}
                          value={passwords[i.name] ?? ""} onChange={(e) => setPasswords({ ...passwords, [i.name]: e.target.value })} />
                        <Button variant="secondary" disabled={!passwords[i.name]} onClick={() => act(async () => {
                          await api.setSecret(project.id, i.name, passwords[i.name], "password"); setPasswords({ ...passwords, [i.name]: "" }); await reload();
                        }, `Password for ${i.name} stored in memory`)}>Set</Button>
                      </div>
                    )}
                    <div className="font-mono text-[11px] text-mute">
                      {i.token_env && <>${i.token_env}</>}{i.login && <> · login {i.login.method} {i.login.path}</>}
                    </div>
                  </div>
                )}
                {anon && <p className="text-xs text-mute">No credentials. The Unauthenticated module and the matrix&apos;s guest column use this identity.</p>}
              </div>
            );
          })}
        </div>

        <Card>
          <CardHeader title="Add an identity" />
          <CardBody className="grid grid-cols-2 items-end gap-3 md:grid-cols-6">
            <Field label="Name"><Input value={ni.name} onChange={(e) => setNi({ ...ni, name: e.target.value })} placeholder="alice" /></Field>
            <Field label="Role"><Input value={ni.role} disabled={ni.authType === "none"} onChange={(e) => setNi({ ...ni, role: e.target.value })} placeholder="user | admin" /></Field>
            <Field label="Tenant"><Input value={ni.tenant} onChange={(e) => setNi({ ...ni, tenant: e.target.value })} placeholder="acme" /></Field>
            <Field label="Authentication"><Select value={ni.authType} onChange={(e) => setNi({ ...ni, authType: e.target.value })}>
              <option value="bearer">Bearer token</option><option value="header">Custom header</option><option value="cookie">Session cookie</option>
              <option value="query">API key in query</option><option value="basic">HTTP Basic</option><option value="none">None (guest)</option></Select></Field>
            {ni.authType === "query" ? (
              <Field label="Query parameter"><Input value={ni.queryName} onChange={(e) => setNi({ ...ni, queryName: e.target.value })} /></Field>
            ) : ni.authType === "basic" ? (
              <Field label="Username" hint="empty: secret is user:password"><Input value={ni.username} onChange={(e) => setNi({ ...ni, username: e.target.value })} /></Field>
            ) : (
              <Field label="Header name"><Input value={ni.header} disabled={ni.authType !== "header"} onChange={(e) => setNi({ ...ni, header: e.target.value })} /></Field>
            )}
            <Button variant="accent" disabled={!ni.name.trim()} onClick={addIdentity}><Plus className="size-4" /> Add</Button>
            <Field label="Login endpoint (optional)" hint='POST {"username", "password"}; token taken from the JSON response' className="col-span-2 md:col-span-4">
              <Input className="font-mono" value={ni.loginPath} disabled={ni.authType === "none"} onChange={(e) => setNi({ ...ni, loginPath: e.target.value })} placeholder="/api/auth/login" />
            </Field>
            <Field label="Token field in response" className="col-span-2">
              <Input className="font-mono" value={ni.tokenPath} disabled={!ni.loginPath} onChange={(e) => setNi({ ...ni, tokenPath: e.target.value })} />
            </Field>
          </CardBody>
        </Card>
      </section>

      <section className="space-y-6">
        <SectionTitle title="Test objects and their owners" hint="BOLA tests compare the owner's request with other identities requesting the same object." />
        <Card>
          <div className="overflow-x-auto px-3 pt-3">
            <table className="w-full text-left text-sm">
              <thead className="text-[11px] uppercase tracking-[0.12em] text-mute"><tr>
                <th className="px-4 py-3 font-semibold">Type</th><th className="font-semibold">Object id</th><th className="font-semibold">Owner</th>
                <th className="font-semibold">Tenant</th><th className="font-semibold">Parent</th><th className="font-semibold">Match rules</th><th />
              </tr></thead>
              <tbody>
                {project.resources.map((r, idx) => (
                  <tr key={r.type + r.id} className="border-t border-line/60">
                    <td className="px-4 py-2.5"><Badge tone="info">{r.type}</Badge></td>
                    <td className="font-mono font-semibold">{r.id}</td>
                    <td>{r.owner ?? <span className="text-warn">no owner</span>}</td>
                    <td className="font-mono text-mute">{r.tenant ?? "(from owner)"}</td>
                    <td className="font-mono text-mute">{r.parent ?? "-"}</td>
                    <td className="font-mono text-[11px] text-mute">{r.match && Object.keys(r.match).length
                      ? Object.entries(r.match).map(([k, v]) => `${k} = ${v}`).join("; ") : "-"}</td>
                    <td className="pr-2 text-right"><Button size="icon" variant="ghost" onClick={() => saveResources(project.resources.filter((_, j) => j !== idx))}><Trash2 className="size-4" /></Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <CardBody className="grid grid-cols-2 items-end gap-3 border-t border-line/60 pt-5 md:grid-cols-6">
            <Field label="Type"><Input value={nr.type} onChange={(e) => setNr({ ...nr, type: e.target.value })} /></Field>
            <Field label="Object id"><Input value={nr.id} onChange={(e) => setNr({ ...nr, id: e.target.value })} placeholder="101" /></Field>
            <Field label="Owner"><Select value={nr.owner} onChange={(e) => setNr({ ...nr, owner: e.target.value })}>
              <option value="">-</option>{owners.map((o) => <option key={o.name}>{o.name}</option>)}</Select></Field>
            <Field label="Tenant"><Input value={nr.tenant} onChange={(e) => setNr({ ...nr, tenant: e.target.value })} /></Field>
            <Field label="Parent" hint="nested paths, e.g. user:1"><Input value={nr.parent} onChange={(e) => setNr({ ...nr, parent: e.target.value })} placeholder="user:1" /></Field>
            <Field label="Match rules (optional)" hint="Composite ids: JSONPath=value; separated by ;" className="col-span-2 md:col-span-5">
              <Input className="font-mono" value={nr.match} onChange={(e) => setNr({ ...nr, match: e.target.value })} placeholder="$.tenant=acme; $.number=101" />
            </Field>
            <Button variant="accent" disabled={!nr.type || !nr.id} onClick={() => {
              saveResources([...project.resources, { type: nr.type, id: nr.id, owner: nr.owner || null, tenant: nr.tenant || null, id_field: "id", parent: nr.parent || null, match: parseMatch(nr.match) }]);
              setNr({ ...nr, id: "", match: "" });
            }}><Plus className="size-4" /> Add object</Button>
          </CardBody>
        </Card>
      </section>
    </div>
  );
}
