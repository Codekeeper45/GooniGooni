/**
 * ErrorBoundary — catches unhandled React render errors and shows a fallback UI
 * instead of a white screen. Wraps the entire application.
 */

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    console.error("[ErrorBoundary] Uncaught error:", error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div
          className="min-h-screen flex items-center justify-center p-6"
          style={{ background: "#0B0E14", fontFamily: "'Space Grotesk', sans-serif" }}
        >
          <div
            className="max-w-md w-full p-8 rounded-2xl text-center"
            style={{ background: "#141820", border: "1px solid rgba(239,68,68,0.2)" }}
          >
            <div
              className="w-16 h-16 mx-auto mb-4 rounded-full flex items-center justify-center text-2xl"
              style={{ background: "rgba(239,68,68,0.1)" }}
            >
              ⚠️
            </div>
            <h2
              className="text-lg font-semibold mb-2"
              style={{ color: "#E5E7EB" }}
            >
              Что-то пошло не так
            </h2>
            <p
              className="text-sm mb-1"
              style={{ color: "#9CA3AF" }}
            >
              Произошла непредвиденная ошибка. Попробуйте перезагрузить страницу.
            </p>
            {this.state.error && (
              <p
                className="text-xs mb-6 break-all"
                style={{ color: "#6B7280" }}
              >
                {this.state.error.message}
              </p>
            )}
            <button
              onClick={this.handleReload}
              className="px-6 py-2.5 rounded-xl text-sm font-medium transition-all"
              style={{
                background: "linear-gradient(135deg, #4F8CFF, #3B6FD9)",
                color: "#fff",
                boxShadow: "0 2px 8px rgba(79,140,255,0.25)",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-1px)";
                e.currentTarget.style.boxShadow = "0 4px 12px rgba(79,140,255,0.35)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "translateY(0)";
                e.currentTarget.style.boxShadow = "0 2px 8px rgba(79,140,255,0.25)";
              }}
            >
              Перезагрузить
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
