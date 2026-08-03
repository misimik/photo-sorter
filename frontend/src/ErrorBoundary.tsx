import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: unknown) {
    console.error("Photo Sorter crashed:", error, info);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-screen w-screen bg-neutral-950 text-neutral-100 flex flex-col items-center justify-center gap-4 p-8">
          <h1 className="text-xl font-semibold text-red-400">Something went wrong</h1>
          <pre className="text-sm bg-neutral-900 border border-neutral-800 rounded p-4 max-w-2xl overflow-auto whitespace-pre-wrap">
            {this.state.error.message}
            {"\n\n"}
            {this.state.error.stack}
          </pre>
          <button
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 rounded"
            onClick={() => location.reload()}
          >
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
