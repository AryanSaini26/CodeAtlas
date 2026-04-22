import { Component, type ErrorInfo, type ReactNode } from "react";
import { Icon } from "./Icon";

type Props = {
  children: ReactNode;
  fallback?: (err: Error, reset: () => void) => ReactNode;
};

type State = { error: Error | null };

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    if (typeof console !== "undefined") {
      console.error("[CodeAtlas ErrorBoundary]", error, info.componentStack);
    }
  }

  reset = () => this.setState({ error: null });

  render() {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);
    return <DefaultFallback error={error} reset={this.reset} />;
  }
}

function DefaultFallback({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="flex items-center justify-center min-h-[50vh] p-6">
      <div className="glass rounded-[12px] max-w-[520px] w-full p-6 flex flex-col gap-4">
        <div className="flex items-center gap-2">
          <div
            className="flex items-center justify-center w-8 h-8 rounded-full"
            style={{ backgroundColor: "rgba(239,68,68,0.12)", color: "#ef4444" }}
          >
            <Icon name="alert" size={16} />
          </div>
          <div className="font-head font-bold text-[15px] text-text-1">
            Something broke in this view
          </div>
        </div>
        <div className="text-[12px] text-text-3 leading-relaxed">
          The rest of CodeAtlas is still running. This is a UI-side error —
          often caused by a failed API call or stale data.
        </div>
        <pre className="bg-black/40 rounded-md p-3 text-[11px] font-mono text-red-300 overflow-auto max-h-[160px] whitespace-pre-wrap break-words">
          {error.message || String(error)}
        </pre>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={reset}
            className="px-3 py-1.5 rounded-md border border-cyan/40 bg-cyan/[0.08] text-cyan text-[12px] font-medium hover:bg-cyan/[0.14] transition-colors"
          >
            Try again
          </button>
          <button
            type="button"
            onClick={() => (window.location.href = "/")}
            className="px-3 py-1.5 rounded-md border border-border bg-white/[0.02] text-text-2 text-[12px] hover:bg-white/[0.05] transition-colors"
          >
            Back to Dashboard
          </button>
        </div>
      </div>
    </div>
  );
}
