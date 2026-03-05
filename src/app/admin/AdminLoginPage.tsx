import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import {
  clearSession,
  createAdminSession,
  ensureAdminSession,
  AdminHttpError,
  isAdminSessionErrorCode,
} from "./adminSession";

export function AdminLoginPage() {
  const nav = useNavigate();
  const [login, setLogin] = useState("admin");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [retryAfterSeconds, setRetryAfterSeconds] = useState(0);

  useEffect(() => {
    ensureAdminSession()
      .then(() => nav("/admin/dashboard"))
      .catch((err: unknown) => {
        if (err instanceof AdminHttpError && isAdminSessionErrorCode(err.code)) {
          clearSession();
        }
      });
  }, [nav]);

  useEffect(() => {
    if (retryAfterSeconds <= 0) return;
    const timer = window.setInterval(() => {
      setRetryAfterSeconds((value) => (value > 1 ? value - 1 : 0));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [retryAfterSeconds]);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    const userLogin = login.trim();
    const userPassword = password;

    if (!userLogin || !userPassword) {
      setError("Fill all fields");
      return;
    }
    if (retryAfterSeconds > 0) {
      setError(`Too many attempts. Retry in ${retryAfterSeconds}s.`);
      return;
    }

    try {
      setLoading(true);
      await createAdminSession(userLogin, userPassword);
      nav("/admin/dashboard");
    } catch (err: unknown) {
      if (err instanceof AdminHttpError) {
        if (err.status === 429) {
          const retryAfter = err.retryAfterSeconds ?? 60;
          setRetryAfterSeconds(retryAfter);
          const source = err.code === "admin_login_rate_limited" ? "login attempts limit" : "admin API rate limit";
          setError(`Too many admin requests (${source}). Retry in ${retryAfter}s.`);
          return;
        }
        setError(err.message || "Authentication failed");
        return;
      }
      setError(err instanceof Error ? err.message : "Authentication failed");
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
        Back to app
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
          <div style={{ fontSize: 40, marginBottom: 8 }}>Admin</div>
          <h1 style={{ color: "#fff", margin: 0, fontSize: 24, fontWeight: 700 }}>
            Gooni Admin
          </h1>
          <div style={{
            margin: "12px auto 0",
            padding: "8px 16px",
            background: "rgba(234,179,8,0.12)",
            border: "1px solid rgba(234,179,8,0.3)",
            borderRadius: 8,
            color: "#fde68a",
            fontSize: 13,
            fontWeight: 500,
            maxWidth: 280,
          }}>
            🔑 Пароль по умолчанию: <strong>admin</strong>
          </div>
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
              Login
            </label>
            <input
              type="text"
              value={login}
              onChange={(e) => setLogin(e.target.value)}
              placeholder="admin"
              autoComplete="username"
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
              Password
            </label>
            <div style={{ position: "relative" }}>
              <input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter admin password"
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
                onClick={() => setShowPassword((v) => !v)}
                style={{
                  position: "absolute",
                  right: 12,
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  color: "rgba(255,255,255,0.5)",
                  fontSize: 14,
                  padding: 0,
                }}
              >
                {showPassword ? "Hide" : "Show"}
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
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading || retryAfterSeconds > 0}
            style={{
              width: "100%",
              padding: "13px 0",
              borderRadius: 10,
              background: "linear-gradient(135deg,#7c3aed,#a855f7)",
              border: "none",
              color: "#fff",
              fontWeight: 700,
              fontSize: 15,
              cursor: loading || retryAfterSeconds > 0 ? "default" : "pointer",
              opacity: loading || retryAfterSeconds > 0 ? 0.7 : 1,
              transition: "opacity 0.2s",
              boxShadow: "0 4px 16px rgba(124,58,237,0.4)",
            }}
          >
            {loading ? "Checking..." : retryAfterSeconds > 0 ? `Retry in ${retryAfterSeconds}s` : "Sign in"}
          </button>
        </form>

        <p style={{ textAlign: "center", marginTop: 24, color: "rgba(255,255,255,0.3)", fontSize: 12 }}>
          Admin session is stored in secure cookie only.
        </p>
      </div>
    </div>
  );
}
