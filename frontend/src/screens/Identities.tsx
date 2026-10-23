import { KeyRound, Plus, Trash2, UserRound } from "lucide-react";
import { useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader } from "@/components/ui/card";
import { Field, Input, Select } from "@/components/ui/field";
import { useAction, useApp } from "@/ctx";
import { api, type Identity, type Resource } from "@/lib/api";
import { PageHeader } from "./common";

const SOURCE_LABEL: Record<string, { text: string; tone: "ok" | "warn" | "mute" | "bad" }> = {
  runtime: { text: "token set (memory only)", tone: "ok" },
  env: { text: "from environment variable", tone: "ok" },
  login: { text: "token via login flow", tone: "ok" },
  missing: { text: "no token", tone: "bad" },
  none: { text: "anonymous", tone: "mute" },
};

export function Identities() {
  const { project, reload } = useApp();
  const act = useAction();
  const [tokens, setTokens] = useState<Record<string, string>>({});
  const [ni, setNi] = useState({ name: "", role: "user", tenant: "", authType: "bearer", header: "X-API-Key", loginPath: "", tokenPath: "access_token" });
  const [passwords, setPasswords] = useState<Record<string, string>>({});
  const [nr, setNr] = useState({ type: "order", id: "", owner: "", tenant: "" });

  const addIdentity = () => act(async () => {
    const anon = ni.authType === "none";
    await api.putIdentity(project.id, {
      name: ni.name.trim(), role: anon ? "guest" : ni.role, tenant: ni.tenant || null,
      auth: { type: ni.authType as Identity["auth"]["type"], header_name: ni.header, cookie_name: "session" },
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
    <div className="space-y-6">
      <PageHeader title="Identity Manager" hint="Test accounts with their roles and tenants, and which objects belong to whom." />

      <Card>
        <CardHeader title="Test identities"
          hint="Tokens are write-only: kept in server memory for this session, never saved to the database, config or reports. Alternatively export the env variable shown below before starting AuthScope." />
        <div className="divide-y divide-line">
          {project.identities.map((i) => {
            const src = SOURCE_LABEL[i.secret_source ?? "missing"];
            return (
              <div key={i.name} className="flex items-center gap-4 px-5 py-3">
                <div className="grid size-8 place-items-center rounded-full bg-panel2"><UserRound className="size-4 text-mute" /></div>
                <div className="w-40">
                  <div className="font-medium">{i.name}</div>
                  <div className="text-xs text-mute">role <span className="font-mono text-ink">{i.role}</span>{i.tenant && <> - tenant <span className="font-mono text-ink">{i.tenant}</span></>}</div>
                </div>
                <div className="w-52">
                  <Badge tone={src.tone}>{src.text}</Badge>
                  {i.token_env && <div className="mt-0.5 font-mono text-[11px] text-mute">${i.token_env}</div>}
                  {i.login && <div className="mt-0.5 font-mono text-[11px] text-mute">login: {i.login.method} {i.login.path}</div>}
                </div>
                <div className="flex flex-1 items-center gap-2">
                  {i.auth.type !== "none" && (
                    <>
                      <Input type="password" autoComplete="off" placeholder={`${i.auth.type} token`} className="max-w-xs font-mono"
                        value={tokens[i.name] ?? ""} onChange={(e) => setTokens({ ...tokens, [i.name]: e.target.value })} />
                      <Button size="sm" variant="secondary" disabled={!tokens[i.name]} onClick={() => act(async () => {
                        await api.setSecret(project.id, i.name, tokens[i.name]); setTokens({ ...tokens, [i.name]: "" }); await reload();
                      }, `Token for ${i.name} stored in memory`)}><KeyRound className="size-3.5" /> Set</Button>
                    </>
                  )}
                  {i.login && (
                    <>
                      <Input type="password" autoComplete="off" placeholder={i.password_source === "missing" ? "password for login" : "password set"}
                        className="max-w-[11rem]" value={passwords[i.name] ?? ""} onChange={(e) => setPasswords({ ...passwords, [i.name]: e.target.value })} />
                      <Button size="sm" variant="secondary" disabled={!passwords[i.name]} onClick={() => act(async () => {
                        await api.setSecret(project.id, i.name, passwords[i.name], "password"); setPasswords({ ...passwords, [i.name]: "" }); await reload();
                      }, `Password for ${i.name} stored in memory`)}>Set</Button>
                    </>
                  )}
                </div>
                <Button size="icon" variant="ghost" title="Remove identity" onClick={() => act(async () => { await api.deleteIdentity(project.id, i.name); await reload(); })}><Trash2 className="size-4" /></Button>
              </div>
            );
          })}
          {project.identities.length === 0 && <p className="px-5 py-5 text-sm text-mute">Add at least two user identities and one admin.</p>}
        </div>
        <div className="grid grid-cols-6 items-end gap-2 border-t border-line p-4">
          <Field label="Name"><Input value={ni.name} onChange={(e) => setNi({ ...ni, name: e.target.value })} placeholder="alice" /></Field>
          <Field label="Role"><Input value={ni.role} disabled={ni.authType === "none"} onChange={(e) => setNi({ ...ni, role: e.target.value })} placeholder="user | admin" /></Field>
          <Field label="Tenant (optional)"><Input value={ni.tenant} onChange={(e) => setNi({ ...ni, tenant: e.target.value })} placeholder="acme" /></Field>
          <Field label="Authentication"><Select value={ni.authType} onChange={(e) => setNi({ ...ni, authType: e.target.value })}>
            <option value="bearer">Bearer token</option><option value="header">Custom header</option><option value="cookie">Session cookie</option><option value="none">None (guest)</option></Select></Field>
          <Field label="Header name"><Input value={ni.header} disabled={ni.authType !== "header"} onChange={(e) => setNi({ ...ni, header: e.target.value })} /></Field>
          <Button variant="secondary" disabled={!ni.name.trim()} onClick={addIdentity}><Plus className="size-4" /> Add</Button>
          <Field label="Login endpoint (optional)" hint='POST {"username": name, "password": ...}; the token is taken from the JSON response' className="col-span-3">
            <Input className="font-mono" value={ni.loginPath} disabled={ni.authType === "none"} onChange={(e) => setNi({ ...ni, loginPath: e.target.value })} placeholder="/api/auth/login" />
          </Field>
          <Field label="Token field in response" className="col-span-2">
            <Input className="font-mono" value={ni.tokenPath} disabled={!ni.loginPath} onChange={(e) => setNi({ ...ni, tokenPath: e.target.value })} />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader title="Test objects and their owners" hint="BOLA tests compare the owner's request against other identities requesting the same object." />
        <table className="w-full text-left text-sm">
          <thead className="text-xs text-mute"><tr>
            <th className="px-5 py-2 font-medium">Type</th><th className="font-medium">Object id</th><th className="font-medium">Owner</th><th className="font-medium">Tenant</th><th />
          </tr></thead>
          <tbody>
            {project.resources.map((r, idx) => (
              <tr key={r.type + r.id} className="border-t border-line">
                <td className="px-5 py-2 font-mono">{r.type}</td>
                <td className="font-mono">{r.id}</td>
                <td>{r.owner ?? <span className="text-warn">no owner</span>}</td>
                <td className="font-mono text-mute">{r.tenant ?? "(from owner)"}</td>
                <td className="pr-4 text-right"><Button size="icon" variant="ghost" onClick={() => saveResources(project.resources.filter((_, j) => j !== idx))}><Trash2 className="size-4" /></Button></td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="grid grid-cols-5 items-end gap-2 border-t border-line p-4">
          <Field label="Type"><Input value={nr.type} onChange={(e) => setNr({ ...nr, type: e.target.value })} /></Field>
          <Field label="Object id"><Input value={nr.id} onChange={(e) => setNr({ ...nr, id: e.target.value })} placeholder="101" /></Field>
          <Field label="Owner"><Select value={nr.owner} onChange={(e) => setNr({ ...nr, owner: e.target.value })}>
            <option value="">-</option>{owners.map((o) => <option key={o.name}>{o.name}</option>)}</Select></Field>
          <Field label="Tenant (optional)"><Input value={nr.tenant} onChange={(e) => setNr({ ...nr, tenant: e.target.value })} /></Field>
          <Button variant="secondary" disabled={!nr.type || !nr.id} onClick={() => {
            saveResources([...project.resources, { type: nr.type, id: nr.id, owner: nr.owner || null, tenant: nr.tenant || null, id_field: "id" }]);
            setNr({ ...nr, id: "" });
          }}><Plus className="size-4" /> Add object</Button>
        </div>
      </Card>
      <CardBody className="pt-0 text-xs text-mute">
        Tip: a `guest` identity (no authentication) is what the Unauthenticated module and the matrix's guest column use.
      </CardBody>
    </div>
  );
}
