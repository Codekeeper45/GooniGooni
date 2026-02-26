import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router";
import {
  getSession,
  clearSession,
  adminFetch,
  ensureAdminSession,
  revokeAdminSession,
  type AdminSession,
} from "./adminSession";

interface Account {
  id: string;
  label: string;
  workspace: string | null;
  status: "pending" | "checking" | "ready" | "failed" | "disabled";
  use_count: number;
  last_used: string | null;
  last_error: string | null;
  added_at: string;
}

interface AuditEntry {
  id: number;
  ts: string;
  ip: string;
  action: string;
  details: string;
  success: number;
}

type Tab = "accounts" | "logs";

const statusColors: Record<string, string> = {
  pending: "#f59e0b",
  checking: "#3b82f6",
  ready: "#10b981",
  failed: "#ef4444",
  disabled: "#6b7280",
};
const statusIcons: Record<string, string> = {
  pending: "⏳",
  checking: "🔎",
  ready: "✅",
  failed: "❌",
  disabled: "⏸️",
};

function StatusBadge({ status }: { status: string }) {
  const color = statusColors[status] ?? "#6b7280";
  return (
    <span
      style={{
        background: `${color}22`,
        border: `1px solid ${color}55`,
        color,
        borderRadius: 20,
        padding: "2px 10px",
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      {statusIcons[status] ?? "•"} {status}
    </span>
  );
}

export function AdminDashboard() {
  const nav = useNavigate();
  const session = getSession() as AdminSession | null;

  const [tab, setTab] = useState<Tab>("accounts");
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [logs, setLogs] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<{ msg: string; ok: boolean } | null>(null);

  const [label, setLabel] = useState("");
  const [tokenId, setTokenId] = useState("");
  const [tokenSecret, setTokenSecret] = useState("");
  const [showSecret, setShowSecret] = useState(false);
  const [addLoading, setAddLoading] = useState(false);

  useEffect(() => {
    if (!session) {
      nav("/admin");
      return;
    }
    ensureAdminSession(session.apiUrl).catch(() => {
      clearSession();
      nav("/admin");
    });
  }, [session, nav]);

  const showToast = (msg: string, ok = true) => {
    setToast({ msg, ok });
    setTimeout(() => setToast(null), 3500);
  };

  const fetchAccounts = useCallback(async () => {
    try {
      const res = await adminFetch("/admin/accounts");
      if (res.status === 401 || res.status === 403) {
        clearSession();
        nav("/admin");
        return;
      }
      const data = await res.json();
      setAccounts(data.accounts ?? []);
    } catch {
      // network error
    }
  }, [nav]);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await adminFetch("/admin/logs");
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs ?? []);
      }
    } catch {
      // endpoint can be unavailable during startup
    }
  }, []);

  useEffect(() => {
    setLoading(true);
    Promise.all([fetchAccounts(), fetchLogs()]).finally(() => setLoading(false));
  }, [fetchAccounts, fetchLogs]);

  useEffect(() => {
    const hasActiveChecks = accounts.some((a) => a.status === "pending" || a.status === "checking");
    if (!hasActiveChecks) return;
    const timer = setInterval(fetchAccounts, 5000);
    return () => clearInterval(timer);
  }, [accounts, fetchAccounts]);

  async function doAction(path: string, method = "POST", okMessage = "Готово ✅") {
    try {
      const res = await adminFetch(path, { method });
      if (res.ok) {
        showToast(okMessage || "Готово ✅");
        await fetchAccounts();
      } else {
        showToast(`Ошибка ${res.status}`, false);
      }
    } catch {
      showToast("Сетевая ошибка", false);
    }
  }

  async function handleAddAccount(e: React.FormEvent) {
    e.preventDefault();
    if (!label || !tokenId || !tokenSecret) {
      showToast("Заполните все поля", false);
      return;
    }
    setAddLoading(true);
    try {
      const res = await adminFetch("/admin/accounts", {
        method: "POST",
        body: JSON.stringify({ label, token_id: tokenId, token_secret: tokenSecret }),
      });
      if (res.ok) {
        showToast("✅ Аккаунт добавлен. Проверка запущена.");
        setLabel("");
        setTokenId("");
        setTokenSecret("");
        await fetchAccounts();
      } else {
        const payload = await res.json().catch(() => ({}));
        const detail = payload?.detail?.detail || payload?.detail || res.status;
        showToast(`Ошибка: ${detail}`, false);
      }
    } catch {
      showToast("Сетевая ошибка", false);
    } finally {
      setAddLoading(false);
    }
  }

  async function handleLogout() {
    if (session) {
      await revokeAdminSession(session.apiUrl).catch(() => undefined);
    }
    clearSession();
    nav("/admin");
  }

  const card: React.CSSProperties = {
    background: "rgba(255,255,255,0.05)",
    border: "1px solid rgba(255,255,255,0.1)",
    borderRadius: 14,
    padding: 20,
    marginBottom: 16,
  };
  const input: React.CSSProperties = {
    width: "100%",
    boxSizing: "border-box",
    padding: "10px 12px",
    background: "rgba(255,255,255,0.07)",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: 8,
    color: "#fff",
    fontSize: 14,
    outline: "none",
  };
  const btn = (color: string): React.CSSProperties => ({
    background: color,
    border: "none",
    borderRadius: 7,
    color: "#fff",
    padding: "6px 12px",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer",
  });

  if (!session) return null;

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg,#0f0f1a 0%,#1a0a2e 100%)",
        color: "#fff",
        fontFamily: "Inter,sans-serif",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "18px 28px",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          background: "rgba(0,0,0,0.3)",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontSize: 24 }}>🛡️</span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 18 }}>Gooni Admin</div>
            <div style={{ fontSize: 12, color: "rgba(255,255,255,0.4)" }}>{session.apiUrl}</div>
          </div>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={() => nav("/")}
            style={{
              background: "rgba(255,255,255,0.08)",
              border: "1px solid rgba(255,255,255,0.15)",
              borderRadius: 8,
              color: "rgba(255,255,255,0.7)",
              padding: "7px 16px",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            🏠 На главную
          </button>
          <button
            onClick={handleLogout}
            style={{
              background: "rgba(239,68,68,0.15)",
              border: "1px solid rgba(239,68,68,0.3)",
              borderRadius: 8,
              color: "#fca5a5",
              padding: "7px 16px",
              cursor: "pointer",
              fontSize: 13,
            }}
          >
            🚪 Выйти
          </button>
        </div>
      </div>

      <div
        style={{
          padding: "0 28px",
          borderBottom: "1px solid rgba(255,255,255,0.1)",
          display: "flex",
          gap: 0,
        }}
      >
        {([
          ["accounts", "💳 Аккаунты"],
          ["logs", "📋 Логи"],
        ] as const).map(([t, label2]) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              color: tab === t ? "#a78bfa" : "rgba(255,255,255,0.45)",
              borderBottom: tab === t ? "2px solid #a78bfa" : "2px solid transparent",
              padding: "14px 20px",
              fontWeight: 600,
              fontSize: 14,
              transition: "all 0.2s",
            }}
          >
            {label2}
          </button>
        ))}
      </div>

      <div style={{ padding: "28px", maxWidth: 960, margin: "0 auto" }}>
        {tab === "accounts" && (
          <>
            <div style={card}>
              <h3 style={{ margin: "0 0 16px", fontSize: 16, color: "#c4b5fd" }}>➕ Добавить Modal-аккаунт</h3>
              <form onSubmit={handleAddAccount}>
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "1fr 1fr 1.4fr auto",
                    gap: 10,
                    alignItems: "end",
                  }}
                >
                  <div>
                    <label style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", display: "block", marginBottom: 5 }}>
                      Имя аккаунта
                    </label>
                    <input style={input} placeholder="Workspace 1" value={label} onChange={(e) => setLabel(e.target.value)} required />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", display: "block", marginBottom: 5 }}>
                      Token ID
                    </label>
                    <input style={input} placeholder="ak-xxxx" value={tokenId} onChange={(e) => setTokenId(e.target.value)} required />
                  </div>
                  <div>
                    <label style={{ fontSize: 12, color: "rgba(255,255,255,0.5)", display: "block", marginBottom: 5 }}>
                      Token Secret
                    </label>
                    <div style={{ position: "relative" }}>
                      <input
                        type={showSecret ? "text" : "password"}
                        style={{ ...input, paddingRight: 36 }}
                        placeholder="as-xxxxx"
                        value={tokenSecret}
                        onChange={(e) => setTokenSecret(e.target.value)}
                        required
                      />
                      <button
                        type="button"
                        onClick={() => setShowSecret((v) => !v)}
                        style={{
                          position: "absolute",
                          right: 8,
                          top: "50%",
                          transform: "translateY(-50%)",
                          background: "none",
                          border: "none",
                          color: "rgba(255,255,255,0.4)",
                          cursor: "pointer",
                          fontSize: 14,
                        }}
                      >
                        {showSecret ? "🙈" : "👁️"}
                      </button>
                    </div>
                  </div>
                  <button
                    type="submit"
                    disabled={addLoading}
                    style={{
                      ...btn("linear-gradient(135deg,#7c3aed,#a855f7)"),
                      padding: "10px 18px",
                      fontSize: 13,
                      boxShadow: "0 4px 12px rgba(124,58,237,0.3)",
                    }}
                  >
                    {addLoading ? "⏳" : "➕ Добавить"}
                  </button>
                </div>
              </form>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 16, gap: 10 }}>
              <button
                onClick={() => doAction("/admin/deploy-all", "POST", "🚀 Деплой всех аккаунтов запущен")}
                style={{ ...btn("linear-gradient(135deg,#059669,#10b981)"), padding: "8px 18px", fontSize: 13 }}
              >
                🚀 Задеплоить все
              </button>
              <button
                onClick={fetchAccounts}
                style={{ ...btn("rgba(255,255,255,0.1)"), padding: "8px 18px", fontSize: 13 }}
              >
                🔄 Обновить
              </button>
            </div>

            {loading ? (
              <div style={{ textAlign: "center", color: "rgba(255,255,255,0.4)", padding: 40 }}>⏳ Загрузка...</div>
            ) : accounts.length === 0 ? (
              <div style={{ ...card, textAlign: "center", padding: 40, color: "rgba(255,255,255,0.35)" }}>
                <div style={{ fontSize: 40, marginBottom: 10 }}>📭</div>
                Нет аккаунтов. Добавьте первый выше.
              </div>
            ) : (
              <div style={card}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                      {["Имя", "Workspace", "Статус", "Запросов", "Последний", "Действия"].map((h) => (
                        <th
                          key={h}
                          style={{
                            textAlign: "left",
                            color: "rgba(255,255,255,0.45)",
                            fontSize: 12,
                            fontWeight: 600,
                            padding: "6px 8px",
                          }}
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((acc) => (
                      <tr key={acc.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                        <td style={{ padding: "10px 8px", fontWeight: 600, fontSize: 14 }}>{acc.label}</td>
                        <td style={{ padding: "10px 8px", fontSize: 13, color: "rgba(255,255,255,0.55)" }}>{acc.workspace ?? "—"}</td>
                        <td style={{ padding: "10px 8px" }}>
                          <StatusBadge status={acc.status} />
                          {acc.last_error && (
                            <div
                              title={acc.last_error}
                              style={{
                                fontSize: 11,
                                color: "#fca5a5",
                                marginTop: 2,
                                maxWidth: 180,
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                            >
                              {acc.last_error}
                            </div>
                          )}
                        </td>
                        <td style={{ padding: "10px 8px", fontSize: 13, textAlign: "center" }}>{acc.use_count}</td>
                        <td style={{ padding: "10px 8px", fontSize: 12, color: "rgba(255,255,255,0.4)" }}>
                          {acc.last_used ? new Date(acc.last_used).toLocaleString("ru-RU") : "—"}
                        </td>
                        <td style={{ padding: "10px 8px" }}>
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                            <button
                              onClick={() => doAction(`/admin/accounts/${acc.id}/deploy`, "POST", "🚀 Проверка аккаунта запущена")}
                              style={btn("#1d4ed8")}
                              title="Re-deploy"
                            >
                              🚀
                            </button>
                            {acc.status !== "disabled" ? (
                              <button
                                onClick={() => doAction(`/admin/accounts/${acc.id}/disable`, "POST", "⏸ Аккаунт отключён")}
                                style={btn("#92400e")}
                                title="Отключить"
                              >
                                ⏸
                              </button>
                            ) : (
                              <button
                                onClick={() => doAction(`/admin/accounts/${acc.id}/enable`, "POST", "▶ Аккаунт включён")}
                                style={btn("#065f46")}
                                title="Включить"
                              >
                                ▶
                              </button>
                            )}
                            <button
                              onClick={() => {
                                if (confirm(`Удалить аккаунт "${acc.label}"?`)) {
                                  doAction(`/admin/accounts/${acc.id}`, "DELETE", "🗑 Аккаунт удалён");
                                }
                              }}
                              style={btn("#7f1d1d")}
                              title="Удалить"
                            >
                              🗑
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {tab === "logs" && (
          <div style={card}>
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 16 }}>
              <h3 style={{ margin: 0, fontSize: 16, color: "#c4b5fd" }}>📋 Журнал действий</h3>
              <button
                onClick={fetchLogs}
                style={{ ...btn("rgba(255,255,255,0.1)"), padding: "6px 14px", fontSize: 12 }}
              >
                🔄 Обновить
              </button>
            </div>
            {logs.length === 0 ? (
              <div style={{ textAlign: "center", color: "rgba(255,255,255,0.35)", padding: 30 }}>Нет записей</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid rgba(255,255,255,0.1)" }}>
                    {["Время", "IP", "Действие", "Детали", "OK"].map((h) => (
                      <th
                        key={h}
                        style={{
                          textAlign: "left",
                          color: "rgba(255,255,255,0.45)",
                          fontSize: 12,
                          fontWeight: 600,
                          padding: "6px 8px",
                        }}
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.slice().reverse().map((entry) => (
                    <tr key={entry.id} style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                      <td style={{ padding: "8px", fontSize: 12, color: "rgba(255,255,255,0.45)" }}>
                        {new Date(entry.ts).toLocaleString("ru-RU")}
                      </td>
                      <td style={{ padding: "8px", fontSize: 12, fontFamily: "monospace", color: "#93c5fd" }}>
                        {entry.ip}
                      </td>
                      <td style={{ padding: "8px", fontSize: 13, fontWeight: 600 }}>{entry.action}</td>
                      <td style={{ padding: "8px", fontSize: 12, color: "rgba(255,255,255,0.5)" }}>{entry.details}</td>
                      <td style={{ padding: "8px", fontSize: 14 }}>{entry.success ? "✅" : "❌"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )}
      </div>

      {toast && (
        <div
          style={{
            position: "fixed",
            bottom: 28,
            left: "50%",
            transform: "translateX(-50%)",
            background: toast.ok ? "rgba(16,185,129,0.95)" : "rgba(239,68,68,0.95)",
            color: "#fff",
            padding: "12px 28px",
            borderRadius: 30,
            fontWeight: 600,
            fontSize: 14,
            boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
            zIndex: 9999,
          }}
        >
          {toast.msg}
        </div>
      )}
    </div>
  );
}
