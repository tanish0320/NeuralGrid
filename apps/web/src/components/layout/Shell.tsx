import React from 'react';
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  Clock,
  Compass,
  Cpu,
  Layers,
  Radio,
  RefreshCw,
  Server,
  ShieldAlert,
  Wifi,
} from 'lucide-react';
import { Badge } from '../common/Badge';

export type ScreenId =
  | 'command'
  | 'eventsense'
  | 'twin'
  | 'prediction'
  | 'twinnode'
  | 'verification'
  | 'audit';

interface ShellProps {
  currentScreen: ScreenId;
  onSelectScreen: (screen: ScreenId) => void;
  isBackendConnected: boolean;
  isWsConnected: boolean;
  tick: number;
  simTime: string;
  seed: number;
  runId: string | null;
  onResetDemo: () => void;
  isResetting: boolean;
  children: React.ReactNode;
}

export const Shell: React.FC<ShellProps> = ({
  currentScreen,
  onSelectScreen,
  isBackendConnected,
  isWsConnected,
  tick,
  simTime,
  seed,
  runId,
  onResetDemo,
  isResetting,
  children,
}) => {
  const navItems: { id: ScreenId; label: string; icon: React.ReactNode }[] = [
    { id: 'command', label: 'Command Centre', icon: <Activity className="w-4 h-4" /> },
    { id: 'eventsense', label: 'EventSense', icon: <Compass className="w-4 h-4" /> },
    { id: 'twin', label: 'Network Twin', icon: <Layers className="w-4 h-4" /> },
    { id: 'prediction', label: 'Prediction & Plans', icon: <Brain className="w-4 h-4" /> },
    { id: 'twinnode', label: 'TwinNode Live Lab', icon: <Cpu className="w-4 h-4" /> },
    { id: 'verification', label: 'Verification', icon: <CheckCircle2 className="w-4 h-4" /> },
    { id: 'audit', label: 'Governance / Audit', icon: <ShieldAlert className="w-4 h-4" /> },
  ];

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-noc-bg text-slate-100 font-sans">
      {/* Left Navigation Rail */}
      <aside className="w-64 flex-shrink-0 flex flex-col border-r border-noc-border bg-noc-surface">
        {/* Brand */}
        <div className="h-16 flex items-center px-5 border-b border-noc-border gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-noc-cyan to-noc-teal flex items-center justify-center shadow-lg shadow-noc-cyan/20">
            <Radio className="w-4 h-4 text-slate-950 font-bold" />
          </div>
          <div>
            <div className="font-bold tracking-tight text-sm text-slate-100 flex items-center gap-1.5">
              <span>NeuralGrid</span>
              <span className="text-[10px] font-mono px-1.5 py-0.2 bg-noc-cyan/20 text-noc-cyan rounded border border-noc-cyan/30">
                v1.5
              </span>
            </div>
            <div className="text-[11px] text-slate-400 font-mono tracking-tight">
              Proactive Telecom NOC
            </div>
          </div>
        </div>

        {/* Navigation Menu */}
        <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
          {navItems.map((item) => {
            const active = currentScreen === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectScreen(item.id)}
                className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-md text-xs font-medium transition-all ${
                  active
                    ? 'bg-noc-card text-noc-cyan border border-noc-cyan/40 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200 hover:bg-noc-hover'
                }`}
              >
                <span className={active ? 'text-noc-cyan' : 'text-slate-400'}>{item.icon}</span>
                <span>{item.label}</span>
              </button>
            );
          })}
        </nav>

        {/* Epistemic Attribution & System Footer */}
        <div className="p-3 border-t border-noc-border bg-noc-surface text-[10px] text-slate-400 space-y-2 font-mono">
          <div className="flex items-center justify-between">
            <span className="text-slate-500">OPERATOR:</span>
            <span className="text-slate-300 font-semibold">Tanish (Lead)</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-slate-500">PLATFORM:</span>
            <span className="text-slate-300">Nokia Demo Build</span>
          </div>
          <div className="pt-2 border-t border-noc-divider text-[9px] text-slate-500 leading-tight">
            EventSense Powered by Crawl4AI, GDELT DOC & Feedparser
          </div>
        </div>
      </aside>

      {/* Main Container */}
      <div className="flex-1 flex flex-col h-full overflow-hidden">
        {/* Top Control Bar */}
        <header className="h-16 flex-shrink-0 border-b border-noc-border bg-noc-surface px-6 flex items-center justify-between">
          {/* Left Metadata Chips */}
          <div className="flex items-center gap-3">
            <Badge type="SYNTHETIC" label="SIMULATED NOC" />
            <div className="h-4 w-px bg-noc-border" />
            <div className="flex items-center gap-2 text-xs font-mono text-slate-300">
              <span className="text-slate-500">RUN:</span>
              <span className="text-noc-cyan truncate max-w-[120px]" title={runId || 'N/A'}>
                {runId ? runId.substring(0, 8) + '...' : 'INITIAL'}
              </span>
            </div>
            <div className="h-4 w-px bg-noc-border" />
            <div className="text-xs font-mono text-slate-400">
              <span className="text-slate-500">SEED:</span> {seed}
            </div>
            <div className="h-4 w-px bg-noc-border" />
            <div className="text-xs font-mono text-slate-400">
              <span className="text-slate-500">CELLS:</span> 100
            </div>
          </div>

          {/* Right Status Indicators & Reset Control */}
          <div className="flex items-center gap-4">
            {/* Clock & Tick */}
            <div className="flex items-center gap-2 bg-noc-card px-3 py-1.5 rounded border border-noc-border text-xs font-mono">
              <Clock className="w-3.5 h-3.5 text-noc-cyan" />
              <span className="text-slate-300">Tick {tick}</span>
              <span className="text-slate-500">|</span>
              <span className="text-slate-400">{simTime.substring(11, 19)} UTC</span>
            </div>

            {/* Backend API Connection */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono border ${
                isBackendConnected
                  ? 'bg-emerald-950/40 border-emerald-600/50 text-emerald-300'
                  : 'bg-red-950/40 border-red-600/50 text-red-400 animate-pulse'
              }`}
            >
              <div
                className={`w-2 h-2 rounded-full ${
                  isBackendConnected ? 'bg-emerald-400' : 'bg-red-400'
                }`}
              />
              <span>API: {isBackendConnected ? 'ONLINE' : 'DISCONNECTED'}</span>
            </div>

            {/* WebSocket Stream */}
            <div
              className={`flex items-center gap-1.5 px-2.5 py-1 rounded text-[11px] font-mono border ${
                isWsConnected
                  ? 'bg-cyan-950/40 border-cyan-600/50 text-cyan-300'
                  : 'bg-amber-950/40 border-amber-600/50 text-amber-400'
              }`}
            >
              <Wifi className="w-3 h-3" />
              <span>WS: {isWsConnected ? 'LIVE' : 'CONNECTING'}</span>
            </div>

            {/* Reset Demo Button */}
            <button
              onClick={onResetDemo}
              disabled={isResetting}
              className="flex items-center gap-1.5 px-3 py-1.5 bg-noc-card hover:bg-noc-hover border border-noc-border text-xs font-mono font-medium text-slate-200 rounded transition active:scale-95 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${isResetting ? 'animate-spin' : ''}`} />
              <span>Reset Demo</span>
            </button>
          </div>
        </header>

        {/* Viewport Content */}
        <main className="flex-1 overflow-auto bg-noc-bg p-5">
          {children}
        </main>
      </div>
    </div>
  );
};
