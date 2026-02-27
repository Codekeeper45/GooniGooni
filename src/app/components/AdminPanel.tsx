import React, { useEffect, useState, useCallback } from "react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface Account {
  id: string;
  label: string;
  workspace: string | null;
  status: "pending" | "checking" | "ready" | "failed" | "disabled";
  use_count: number;
  last_used: string | null;
  last_error: string | null;
  added_at: string;
  failure_type: string | null;
  last_health_check: string | null;
  health_check_result: string | null;
  fail_count: number;
}

// ─── Status badge config ──────────────────────────────────────────────────────

const STATUS_CONFIG = {
  pending:  { label: "⏳ Deploying",  color: "#f59e0b", bg: "rgba(245,158,11,0.15)" },
  checking: { label: "🔍 Checking",  color: "#f59e0b", bg: "rgba(245,158,11,0.15)" },
  ready:    { label: "✅ Ready",       color: "#10b981", bg: "rgba(16,185,129,0.15)" },
  failed:   { label: "❌ Failed",      color: "#ef4444", bg: "rgba(239,68,68,0.15)"  },
  disabled: { label: "⚫ Disabled",   color: "#6b7280", bg: "rgba(107,114,128,0.15)"},
} as const;

const FAILURE_TYPE_CONFIG: Record<string, { label: string; color: string; bg: string; icon: string }> = {
  quota_exceeded:      { label: "Quota",     color: "#ef4444", bg: "rgba(239,68,68,0.12)",  icon: "💰" },
  auth_failed:         { label: "Auth",      color: "#ef4444", bg: "rgba(239,68,68,0.12)",  icon: "🔑" },
  timeout:             { label: "Timeout",   color: "#f59e0b", bg: "rgba(245,158,11,0.12)", icon: "⏱️" },
  container_failed:    { label: "Container", color: "#f59e0b", bg: "rgba(245,158,11,0.12)", icon: "📦" },
  health_check_failed: { label: "Health",    color: "#f59e0b", bg: "rgba(245,158,11,0.12)", icon: "🏥" },
  unknown:             { label: "Unknown",   color: "#6b7280", bg: "rgba(107,114,128,0.12)",icon: "❓" },
};

// ─── API helper ───────────────────────────────────────────────────────────────

const API_URL = ((import.meta as any).env.VITE_API_URL as string | undefined) ?? "";

async function adminFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const ADMIN_KEY = localStorage.getItem("mg_admin_key") ?? "";
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "x-admin-key": ADMIN_KEY,
      ...((options.headers as Record<string, string>) ?? {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? res.statusText);
  }
  return res.json();
}

// ─── Component ────────────────────────────────────────────────────────────────

interface AdminPanelProps {
  onClose?: () => void;
}

export const AdminPanel: React.FC<AdminPanelProps> = ({ onClose }) => {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deployingAll, setDeployingAll] = useState(false);

  // Add form state
  const [showForm, setShowForm] = useState(false);
  const [formLabel, setFormLabel] = useState("");
  const [formTokenId, setFormTokenId] = useState("");
  const [formTokenSecret, setFormTokenSecret] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Security & Secrets state
  const [apiKey, setApiKey] = useState(() => localStorage.getItem("mg_api_key") ?? "");
  const [adminKey, setAdminKey] = useState(() => localStorage.getItem("mg_admin_key") ?? "");
  const [securitySuccess, setSecuritySuccess] = useState(false);

  const handleSaveSecurity = (e: React.FormEvent) => {
    e.preventDefault();
    localStorage.setItem("mg_api_key", apiKey.trim());
    localStorage.setItem("mg_admin_key", adminKey.trim());
    setSecuritySuccess(true);
    setTimeout(() => setSecuritySuccess(false), 3000);
    // Optionally reload to apply keys globally if needed by other components
    // window.location.reload(); 
  };

  // ── Fetch accounts ──────────────────────────────────────────────────────────
  const fetchAccounts = useCallback(async () => {
    if (!API_URL) { setError("VITE_API_URL not configured"); return; }
    try {
      const data = await adminFetch<{ accounts: Account[] }>("/admin/accounts");
      setAccounts(data.accounts);
      setError(null);
    } catch (e: any) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Auto-refresh while any account is in 'pending' or 'checking' state
  useEffect(() => {
    const hasActive = accounts.some((a) => a.status === "pending" || a.status === "checking");
    if (!hasActive) return;
    const timer = setInterval(fetchAccounts, 5000);
    return () => clearInterval(timer);
  }, [accounts, fetchAccounts]);

  // ── Add account ─────────────────────────────────────────────────────────────
  const handleAddAccount = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormSubmitting(true);
    setFormError(null);
    try {
      await adminFetch("/admin/accounts", {
        method: "POST",
        body: JSON.stringify({
          label: formLabel,
          token_id: formTokenId,
          token_secret: formTokenSecret,
        }),
      });
      setFormLabel("");
      setFormTokenId("");
      setFormTokenSecret("");
      setShowForm(false);
      await fetchAccounts();
    } catch (e: any) {
      setFormError(e.message);
    } finally {
      setFormSubmitting(false);
    }
  };

  // ── Actions ─────────────────────────────────────────────────────────────────
  const handleDelete = async (id: string) => {
    if (!confirm("Remove this account from rotation?")) return;
    try {
      await adminFetch(`/admin/accounts/${id}`, { method: "DELETE" });
      await fetchAccounts();
    } catch (e: any) { setError(e.message); }
  };

  const handleDeploy = async (id: string) => {
    try {
      await adminFetch(`/admin/accounts/${id}/deploy`, { method: "POST" });
      await fetchAccounts();
    } catch (e: any) { setError(e.message); }
  };

  const handleDisable = async (id: string) => {
    try {
      await adminFetch(`/admin/accounts/${id}/disable`, { method: "POST" });
      await fetchAccounts();
    } catch (e: any) { setError(e.message); }
  };

  const handleEnable = async (id: string) => {
    try {
      await adminFetch(`/admin/accounts/${id}/enable`, { method: "POST" });
      await fetchAccounts();
    } catch (e: any) { setError(e.message); }
  };

  const handleDeployAll = async () => {
    setDeployingAll(true);
    try {
      await adminFetch("/admin/deploy-all", { method: "POST" });
      await fetchAccounts();
    } catch (e: any) { setError(e.message); }
    finally { setDeployingAll(false); }
  };

  // ─── UI ────────────────────────────────────────────────────────────────────

  const readyCount = accounts.filter((a) => a.status === "ready").length;

  return (
    <div style={styles.overlay}>
      <div style={styles.panel}>
        {/* Header */}
        <div style={styles.header}>
          <div>
            <h2 style={styles.title}>⚙️ Modal Account Manager</h2>
            <p style={styles.subtitle}>
              {readyCount} of {accounts.length} account
              {accounts.length !== 1 ? "s" : ""} in rotation
            </p>
          </div>
          <div style={styles.headerActions}>
            <button
              style={{ ...styles.btn, ...styles.btnSecondary }}
              onClick={handleDeployAll}
              disabled={deployingAll || accounts.length === 0}
            >
              {deployingAll ? "🔄 Deploying…" : "🚀 Deploy All"}
            </button>
            <button
              style={{ ...styles.btn, ...styles.btnPrimary }}
              onClick={() => setShowForm((v) => !v)}
            >
              {showForm ? "✕ Cancel" : "+ Add Account"}
            </button>
            {onClose && (
              <button style={{ ...styles.btn, ...styles.btnGhost }} onClick={onClose}>
                ✕
              </button>
            )}
          </div>
        </div>

        {/* Global error */}
        {error && <div style={styles.errorBanner}>{error}</div>}

        {/* Security & Secrets Section */}
        <div style={styles.securitySection}>
            <h3 style={styles.sectionTitle}>🔒 Security & Secrets</h3>
            <p style={styles.sectionDesc}>
                Manage your API and Admin keys. These are stored locally in your browser.
            </p>
            <form onSubmit={handleSaveSecurity} style={styles.securityForm}>
                <div style={styles.formGrid}>
                    <label style={styles.label}>
                        Gooni API Key
                        <input
                            style={styles.input}
                            type="password"
                            placeholder="Modal API Key"
                            value={apiKey}
                            onChange={(e) => setApiKey(e.target.value)}
                        />
                    </label>
                    <label style={styles.label}>
                        Admin Key
                        <input
                            style={styles.input}
                            type="password"
                            placeholder="Admin Panel Secret"
                            value={adminKey}
                            onChange={(e) => setAdminKey(e.target.value)}
                        />
                    </label>
                </div>
                <div style={styles.securityActions}>
                    {securitySuccess && <span style={styles.successText}>✅ Saved successfully!</span>}
                    <button type="submit" style={{ ...styles.btn, ...styles.btnPrimary }}>
                        Save Keys
                    </button>
                </div>
            </form>
        </div>

        {/* Add Account Form */}
        {showForm && (
          <form onSubmit={handleAddAccount} style={styles.form}>
            <h3 style={styles.formTitle}>Add Modal Account</h3>
            <div style={styles.formGrid}>
              <label style={styles.label}>
                Label
                <input
                  style={styles.input}
                  placeholder="e.g. Account-2"
                  value={formLabel}
                  onChange={(e) => setFormLabel(e.target.value)}
                  required
                />
              </label>
              <label style={styles.label}>
                Token ID
                <input
                  style={styles.input}
                  placeholder="ak-xxxxxxxxxxxx"
                  value={formTokenId}
                  onChange={(e) => setFormTokenId(e.target.value)}
                  required
                />
              </label>
              <label style={{ ...styles.label, gridColumn: "1 / -1" }}>
                Token Secret
                <input
                  style={styles.input}
                  type="password"
                  placeholder="as-xxxxxxxxxxxx"
                  value={formTokenSecret}
                  onChange={(e) => setFormTokenSecret(e.target.value)}
                  required
                />
              </label>
            </div>
            {formError && <p style={styles.formError}>{formError}</p>}
            <div style={styles.formActions}>
              <button
                type="submit"
                style={{ ...styles.btn, ...styles.btnPrimary }}
                disabled={formSubmitting}
              >
                {formSubmitting ? "Adding…" : "➕ Add & Deploy"}
              </button>
            </div>
            <p style={styles.formHint}>
              The account will begin deploying immediately. It will not join rotation until deployment succeeds.
            </p>
          </form>
        )}

        {/* Accounts Table */}
        {accounts.length === 0 ? (
          <div style={styles.empty}>
            <p>No accounts added yet.</p>
            <p style={{ fontSize: "0.85rem", color: "#9ca3af" }}>
              Add a Modal account to enable distributed inference.
            </p>
          </div>
        ) : (
          <div style={styles.tableWrapper}>
            <table style={styles.table}>
              <thead>
                <tr>
                  {["Label", "Workspace", "Status", "Uses", "Last Used", "Actions"].map((h) => (
                    <th key={h} style={styles.th}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {accounts.map((acct) => {
                  const sc = STATUS_CONFIG[acct.status];
                  return (
                    <tr key={acct.id} style={styles.tr}>
                      <td style={styles.td}>
                        <strong>{acct.label}</strong>
                      </td>
                      <td style={{ ...styles.td, color: "#9ca3af", fontSize: "0.8rem" }}>
                        {acct.workspace ?? "—"}
                      </td>
                      <td style={styles.td}>
                        <span style={{
                          ...styles.badge,
                          color: sc.color,
                          background: sc.bg,
                        }}>
                          {sc.label}
                        </span>
                        {acct.failure_type && FAILURE_TYPE_CONFIG[acct.failure_type] && (
                          <span style={{
                            ...styles.badge,
                            color: FAILURE_TYPE_CONFIG[acct.failure_type].color,
                            background: FAILURE_TYPE_CONFIG[acct.failure_type].bg,
                            marginLeft: "0.35rem",
                            fontSize: "0.65rem",
                          }}>
                            {FAILURE_TYPE_CONFIG[acct.failure_type].icon} {FAILURE_TYPE_CONFIG[acct.failure_type].label}
                          </span>
                        )}
                        {acct.last_error && (
                          <p style={styles.errorText} title={acct.last_error}>
                            {acct.last_error.slice(0, 60)}…
                          </p>
                        )}
                        {acct.last_health_check && (
                          <p style={{ margin: "0.15rem 0 0", fontSize: "0.65rem", color: "#6b7280" }}>
                            Health: {acct.health_check_result === "ok" ? "✅" : "❌"}{" "}
                            {new Date(acct.last_health_check).toLocaleTimeString()}
                          </p>
                        )}
                      </td>
                      <td style={{ ...styles.td, textAlign: "center" }}>
                        {acct.use_count}
                      </td>
                      <td style={{ ...styles.td, fontSize: "0.8rem", color: "#9ca3af" }}>
                        {acct.last_used
                          ? new Date(acct.last_used).toLocaleString()
                          : "Never"}
                      </td>
                      <td style={styles.td}>
                        <div style={styles.rowActions}>
                          {/* Re-deploy */}
                          <button
                            style={{ ...styles.iconBtn, color: "#3b82f6" }}
                            title="Re-deploy"
                            onClick={() => handleDeploy(acct.id)}
                          >🚀</button>
                          {/* Disable / Enable */}
                          {acct.status !== "disabled" ? (
                            <button
                              style={{ ...styles.iconBtn, color: "#f59e0b" }}
                              title="Disable"
                              onClick={() => handleDisable(acct.id)}
                            >⏸️</button>
                          ) : (
                            <button
                              style={{ ...styles.iconBtn, color: "#10b981" }}
                              title="Enable"
                              onClick={() => handleEnable(acct.id)}
                            >▶️</button>
                          )}
                          {/* Delete */}
                          <button
                            style={{ ...styles.iconBtn, color: "#ef4444" }}
                            title="Remove"
                            onClick={() => handleDelete(acct.id)}
                          >🗑️</button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

// ─── Styles ───────────────────────────────────────────────────────────────────

const styles: Record<string, React.CSSProperties> = {
  overlay: {
    position: "fixed", inset: 0,
    background: "rgba(0,0,0,0.7)",
    zIndex: 9999,
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: "1rem",
    backdropFilter: "blur(6px)",
  },
  panel: {
    background: "#111827",
    border: "1px solid #1f2937",
    borderRadius: "16px",
    width: "100%", maxWidth: "900px",
    maxHeight: "90vh",
    overflow: "hidden",
    display: "flex", flexDirection: "column",
    boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
  },
  header: {
    display: "flex", alignItems: "flex-start",
    justifyContent: "space-between",
    padding: "1.5rem",
    borderBottom: "1px solid #1f2937",
    gap: "1rem",
  },
  headerActions: { display: "flex", gap: "0.5rem", alignItems: "center", flexShrink: 0 },
  title: { margin: 0, fontSize: "1.25rem", fontWeight: 700, color: "#f9fafb" },
  subtitle: { margin: "0.25rem 0 0", fontSize: "0.85rem", color: "#6b7280" },
  errorBanner: {
    background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.3)",
    color: "#ef4444", padding: "0.75rem 1.5rem", fontSize: "0.875rem",
  },
  form: {
    padding: "1.25rem 1.5rem",
    borderBottom: "1px solid #1f2937",
    background: "#0f172a",
  },
  formTitle: { margin: "0 0 1rem", fontSize: "0.9rem", color: "#d1d5db", fontWeight: 600 },
  formGrid: { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "0.75rem" },
  label: { display: "flex", flexDirection: "column", gap: "0.35rem", fontSize: "0.8rem", color: "#9ca3af" },
  input: {
    background: "#1f2937", border: "1px solid #374151",
    borderRadius: "8px", padding: "0.5rem 0.75rem",
    color: "#f9fafb", fontSize: "0.875rem",
    outline: "none",
  },
  formActions: { display: "flex", justifyContent: "flex-end", marginTop: "1rem" },
  formError: { color: "#ef4444", fontSize: "0.8rem", margin: "0.5rem 0 0" },
  formHint: { fontSize: "0.75rem", color: "#6b7280", margin: "0.5rem 0 0" },
  empty: { padding: "3rem", textAlign: "center", color: "#6b7280" },
  tableWrapper: { overflowY: "auto", flex: 1 },
  table: { width: "100%", borderCollapse: "collapse" },
  th: {
    padding: "0.75rem 1rem", textAlign: "left",
    fontSize: "0.75rem", color: "#6b7280", fontWeight: 600,
    textTransform: "uppercase", letterSpacing: "0.05em",
    borderBottom: "1px solid #1f2937",
    whiteSpace: "nowrap",
  },
  tr: { borderBottom: "1px solid #1f2937", transition: "background 0.15s" },
  td: { padding: "0.875rem 1rem", color: "#d1d5db", verticalAlign: "top" },
  badge: {
    display: "inline-block", padding: "3px 10px",
    borderRadius: "999px", fontSize: "0.75rem", fontWeight: 600,
    whiteSpace: "nowrap",
  },
  errorText: { margin: "0.25rem 0 0", fontSize: "0.7rem", color: "#ef4444" },
  rowActions: { display: "flex", gap: "0.25rem", alignItems: "center" },
  iconBtn: {
    background: "transparent", border: "none",
    cursor: "pointer", fontSize: "1.1rem", padding: "4px",
    borderRadius: "6px", lineHeight: 1,
    transition: "background 0.15s",
  },
  btn: {
    padding: "0.5rem 1rem", borderRadius: "8px",
    border: "none", cursor: "pointer",
    fontSize: "0.875rem", fontWeight: 600,
    transition: "opacity 0.15s",
  },
  btnPrimary: { background: "#6366f1", color: "#fff" },
  btnSecondary: { background: "#1f2937", color: "#d1d5db" },
  btnGhost: { background: "transparent", color: "#6b7280", padding: "0.5rem" },
  securitySection: {
    padding: "1.5rem",
    borderBottom: "1px solid #1f2937",
    background: "rgba(99, 102, 241, 0.03)",
  },
  sectionTitle: { margin: 0, fontSize: "1rem", color: "#f9fafb", fontWeight: 600 },
  sectionDesc: { margin: "0.25rem 0 1rem", fontSize: "0.8rem", color: "#6b7280" },
  securityForm: { display: "flex", flexDirection: "column", gap: "1rem" },
  securityActions: { display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "1rem", marginTop: "0.5rem" },
  successText: { fontSize: "0.8rem", color: "#10b981", fontWeight: 500 },
};

export default AdminPanel;
