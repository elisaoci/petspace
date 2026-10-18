import { useEffect, useState } from "react";
import { Check, Copy, Link2, ShieldOff } from "lucide-react";
import { usePets } from "../context/PetContext";
import { api } from "../lib/api";
import { track } from "../lib/analytics";
import type { AccessGrant, AccessGrantCreated } from "../lib/types";

const SCOPE_LABELS: Record<string, string> = {
  profile: "Профиль питомца",
  records: "Все медзаписи",
  vaccinations: "Прививки",
};

export function AccessPanel() {
  const { pet } = usePets();
  const [grants, setGrants] = useState<AccessGrant[]>([]);
  const [label, setLabel] = useState("");
  const [ttlDays, setTtlDays] = useState(7);
  const [scopes, setScopes] = useState<string[]>(["profile", "records", "vaccinations"]);
  const [created, setCreated] = useState<AccessGrantCreated | null>(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = async (petId: number) => {
    try {
      setGrants(await api<AccessGrant[]>(`/pets/${petId}/access-grants`));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось загрузить доступы.");
    }
  };

  useEffect(() => {
    if (pet) load(pet.id).catch(() => undefined);
    else setGrants([]);
  }, [pet?.id]);

  if (!pet) {
    return <p className="muted">Сначала добавьте питомца.</p>;
  }

  const toggleScope = (scope: string) => {
    setScopes(current =>
      current.includes(scope) ? current.filter(item => item !== scope) : [...current, scope],
    );
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!label.trim() || scopes.length === 0 || busy) return;
    setBusy(true);
    setError("");
    try {
      const grant = await api<AccessGrantCreated>(`/pets/${pet.id}/access-grants`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ label: label.trim(), ttl_days: ttlDays, scopes }),
      });
      setCreated(grant);
      setCopied(false);
      setLabel("");
      await load(pet.id);
      track("access_granted", "/app/smart-id");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось выдать доступ.");
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (grantId: number) => {
    if (!confirm("Отозвать доступ? Ссылка перестанет работать сразу.")) return;
    try {
      await api(`/access-grants/${grantId}/revoke`, { method: "POST" });
      await load(pet.id);
      track("access_revoked", "/app/smart-id");
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось отозвать доступ.");
    }
  };

  const copyLink = async () => {
    if (!created) return;
    const url = `${window.location.origin}${created.url}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      setError("Не удалось скопировать. Выделите ссылку вручную.");
    }
  };

  return (
    <div className="card">
      <div className="card-heading">
        <div>
          <span className="card-kicker">Доступ клиник</span>
          <h3>Ссылка для врача</h3>
        </div>
      </div>
      <p className="muted">
        Клиника видит только выбранные разделы и только до указанной даты. Заметки владельца
        не раскрываются никогда. Ссылку можно отозвать в любой момент.
      </p>

      <form onSubmit={submit} className="record-form">
        <label className="soft-label" htmlFor="grant-label">Кому выдаём</label>
        <input
          className="text-input"
          id="grant-label"
          placeholder="Клиника «Айболит», врач Иванов"
          value={label}
          onChange={event => setLabel(event.target.value)}
          required
        />

        <label className="soft-label" htmlFor="grant-ttl">Срок действия</label>
        <select
          className="text-input"
          id="grant-ttl"
          value={ttlDays}
          onChange={event => setTtlDays(Number(event.target.value))}
        >
          <option value={1}>1 день</option>
          <option value={7}>7 дней</option>
          <option value={30}>30 дней</option>
          <option value={90}>90 дней</option>
        </select>

        <fieldset className="consent-list">
          <legend className="soft-label">Что открываем</legend>
          {Object.entries(SCOPE_LABELS).map(([scope, scopeLabel]) => (
            <label className="consent-item" key={scope}>
              <input
                type="checkbox"
                checked={scopes.includes(scope)}
                onChange={() => toggleScope(scope)}
              />
              <span>{scopeLabel}</span>
            </label>
          ))}
        </fieldset>

        <button className="button primary full-button" type="submit" disabled={busy || scopes.length === 0}>
          {busy ? "Выдаём…" : "Выдать доступ"}
        </button>
      </form>

      {error && <p className="form-error" role="alert">{error}</p>}

      {created && (
        <div className="grant-created">
          <p className="soft-label"><Link2 size={14} /> Ссылка показывается один раз</p>
          <div className="grant-token">
            <code>{`${window.location.origin}${created.url}`}</code>
            <button className="ghost-button" type="button" onClick={() => void copyLink()} aria-label="Скопировать ссылку">
              {copied ? <Check size={16} /> : <Copy size={16} />}
            </button>
          </div>
          <p className="muted">Действует до {new Date(created.expires_at).toLocaleString("ru-RU")}</p>
        </div>
      )}

      <ul className="record-list">
        {grants.map(grant => {
          const revoked = Boolean(grant.revoked_at);
          const expired = new Date(grant.expires_at) <= new Date();
          const status = revoked ? "отозван" : expired ? "истёк" : "активен";
          return (
            <li className="record-row" key={grant.id}>
              <div className="record-meta">
                <strong>{grant.label}</strong>
                <span className="muted">
                  {status} · до {new Date(grant.expires_at).toLocaleDateString("ru-RU")}
                  {grant.last_used_at ? ` · открывали ${new Date(grant.last_used_at).toLocaleDateString("ru-RU")}` : " · ещё не открывали"}
                </span>
                <span className="record-source">{grant.scopes.map(scope => SCOPE_LABELS[scope] ?? scope).join(" · ")}</span>
              </div>
              <div className="record-actions">
                {!revoked && !expired && (
                  <button className="ghost-button" type="button" onClick={() => void revoke(grant.id)}>
                    <ShieldOff size={16} /> Отозвать
                  </button>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
