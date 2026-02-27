import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
  clearSession,
  createAdminSession,
  createHeaderSession,
  ensureAdminSession,
  getSession,
} from "./adminSession";

export function AdminLoginPage() {
  const nav = useNavigate();
  const saved = getSession();
  const [apiUrl, setApiUrl] = useState(saved?.apiUrl ?? "");
  const [adminKey, setAdminKey] = useState("");
  const [error, setError] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const existing = getSession();
    if (!existing) return;
    ensureAdminSession(existing)
      .then(() => nav("/admin/dashboard"))
      .catch(() => clearSession());
  }, [nav]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const url = apiUrl.trim().replace(/\/$/, "");
    const key = adminKey.trim();

    if (!url || !key) {
      setError("Заполните оба поля");
      return;
    }
    if (!url.startsWith("https://") && !url.startsWith("http://")) {
      setError("URL должен начинаться с http:// или https://");
      return;
    }

    try {
      setLoading(true);
      try {
        await createAdminSession(url, key);
      } catch {
        // Fallback mode: stateless admin auth via x-admin-key header.
        await createHeaderSession(url, key);
      }
      nav("/admin/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка авторизации");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      style={{
        minHeight: "100vh",
        background: "linear-gradient(135deg,#0f0f1a 0%,#1a0a2e 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontFamily: "Inter,sans-serif",
        flexDirection: "column",
      }}
    >
      <button
        onClick={() => nav("/")}
        style={{
          position: "fixed",
          top: 18,
          left: 18,
          background: "rgba(255,255,255,0.08)",
          border: "1px solid rgba(255,255,255,0.15)",
          borderRadius: 10,
          color: "rgba(255,255,255,0.7)",
          padding: "8px 16px",
          cursor: "pointer",
          fontSize: 13,
          fontWeight: 600,
          display: "flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        ← На главную
      </button>

      <div
        style={{
          background: "rgba(255,255,255,0.05)",
          backdropFilter: "blur(20px)",
          border: "1px solid rgba(255,255,255,0.12)",
          borderRadius: 20,
          padding: "48px 40px",
          width: "100%",
          maxWidth: 440,
          boxShadow: "0 25px 60px rgba(0,0,0,0.5)",
        }}
      >
        <div style={{ textAlign: "center", marginBottom: 36 }}>
          <div style={{ fontSize: 40, marginBottom: 8 }}>🛡️</div>
          <h1 style={{ color: "#fff", margin: 0, fontSize: 24, fontWeight: 700 }}>
            Gooni Admin
          </h1>
          <p style={{ color: "rgba(255,255,255,0.45)", margin: "6px 0 0", fontSize: 14 }}>
            Управление аккаунтами и деплоем
          </p>
        </div>

        <form onSubmit={handleLogin}>
          <div style={{ marginBottom: 18 }}>
            <label
              style={{
                display: "block",
                color: "rgba(255,255,255,0.7)",
                fontSize: 13,
                marginBottom: 6,
                fontWeight: 600,
              }}
            >
              🌐 Modal Backend URL
            </label>
            <input
              type="url"
              value={apiUrl}
              onChange={(e) => setApiUrl(e.target.value)}
              placeholder="https://workspace--gooni-api.modal.run"
              autoComplete="off"
              required
              style={{
                width: "100%",
                boxSizing: "border-box",
                padding: "12px 14px",
                background: "rgba(255,255,255,0.08)",
                border: "1px solid rgba(255,255,255,0.18)",
                borderRadius: 10,
                color: "#fff",
                fontSize: 14,
                outline: "none",
              }}
            />
          </div>

          <div style={{ marginBottom: 24 }}>
            <label
              style={{
                display: "block",
                color: "rgba(255,255,255,0.7)",
                fontSize: 13,
                marginBottom: 6,
                fontWeight: 600,
              }}
            >
              🔑 Admin Key
            </label>
            <div style={{ position: "relative" }}>
              <input
                type={showKey ? "text" : "password"}
                value={adminKey}
                onChange={(e) => setAdminKey(e.target.value)}
                placeholder="Ваш ADMIN_KEY"
                autoComplete="current-password"
                required
                style={{
                  width: "100%",
                  boxSizing: "border-box",
                  padding: "12px 44px 12px 14px",
                  background: "rgba(255,255,255,0.08)",
                  border: "1px solid rgba(255,255,255,0.18)",
                  borderRadius: 10,
                  color: "#fff",
                  fontSize: 14,
                  outline: "none",
                }}
              />
              <button
                type="button"
                onClick={() => setShowKey((v) => !v)}
                style={{
                  position: "absolute",
                  right: 12,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "rgba(255,255,255,0.5)",
                  fontSize: 16,
                  padding: 0,
                }}
              >
                {showKey ? "🙈" : "👁️"}
              </button>
            </div>
          </div>

          {error && (
            <div
              style={{
                background: "rgba(239,68,68,0.15)",
                border: "1px solid rgba(239,68,68,0.4)",
                borderRadius: 8,
                padding: "10px 14px",
                marginBottom: 16,
                color: "#fca5a5",
                fontSize: 13,
              }}
            >
              ⚠️ {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            style={{
              width: "100%",
              padding: "13px 0",
              borderRadius: 10,
              background: "linear-gradient(135deg,#7c3aed,#a855f7)",
              border: "none",
              color: "#fff",
              fontWeight: 700,
              fontSize: 15,
              cursor: loading ? "default" : "pointer",
              opacity: loading ? 0.7 : 1,
              transition: "opacity 0.2s",
              boxShadow: "0 4px 16px rgba(124,58,237,0.4)",
            }}
          >
            {loading ? "Проверка..." : "Войти в панель"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 24, color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
          Ключ не сохраняется в браузере, хранится только сессионная cookie
        </p>
      </div>
    </div>
  );
}
