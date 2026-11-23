import React, { Component, ErrorInfo, ReactNode } from 'react';
import { AlertTriangle, RefreshCw, Home } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallbackScreen?: () => void;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('NOC Uncaught Render Exception caught by ErrorBoundary:', error, errorInfo);
  }

  private handleReset = () => {
    this.setState({ hasError: false, error: null });
    if (this.props.fallbackScreen) {
      this.props.fallbackScreen();
    }
  };

  public render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-[400px] p-8 bg-noc-surface border border-red-800/60 rounded-xl space-y-5 text-center">
          <div className="w-14 h-14 rounded-full bg-red-950/80 border border-red-500/60 flex items-center justify-center text-red-400">
            <AlertTriangle className="w-8 h-8" />
          </div>
          <div className="space-y-1">
            <h2 className="text-lg font-bold font-mono text-slate-100">Display Module Interrupted</h2>
            <p className="text-xs font-mono text-slate-400 max-w-md">
              A runtime data format discrepancy occurred while rendering this view. The NOC Shell remains active.
            </p>
          </div>
          {this.state.error && (
            <div className="bg-noc-card border border-noc-border p-3 rounded text-[11px] font-mono text-red-300 max-w-lg text-left overflow-x-auto">
              {this.state.error.message}
            </div>
          )}
          <div className="flex items-center gap-3">
            <button
              onClick={this.handleReset}
              className="px-4 py-2 bg-noc-cyan/20 hover:bg-noc-cyan/30 border border-noc-cyan/60 rounded text-xs font-mono font-semibold text-noc-cyan flex items-center gap-2 transition"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              <span>Retry Component</span>
            </button>
            {this.props.fallbackScreen && (
              <button
                onClick={() => {
                  this.setState({ hasError: false, error: null });
                  this.props.fallbackScreen?.();
                }}
                className="px-4 py-2 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-xs font-mono text-slate-300 flex items-center gap-2 transition"
              >
                <Home className="w-3.5 h-3.5" />
                <span>Return to Command Centre</span>
              </button>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}
