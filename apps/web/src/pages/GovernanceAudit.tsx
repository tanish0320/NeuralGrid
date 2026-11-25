import React, { useState, useEffect } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  Clock,
  FileText,
  Filter,
  RefreshCw,
  Search,
  ShieldAlert,
  ShieldCheck,
  User,
} from 'lucide-react';
import { Badge } from '../components/common/Badge';
import { api } from '../services/api';
import { AuditRecord } from '../types/api';

export const GovernanceAudit: React.FC = () => {
  const [logs, setLogs] = useState<AuditRecord[]>([]);
  const [filterText, setFilterText] = useState<string>('');
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [selectedLog, setSelectedLog] = useState<AuditRecord | null>(null);

  const loadLogs = async () => {
    setIsLoading(true);
    try {
      const data = await api.getAuditLogs(150);
      setLogs(data);
    } catch (_) {
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadLogs();
  }, []);

  const filteredLogs = logs.filter(
    (l) =>
      l.action.toLowerCase().includes(filterText.toLowerCase()) ||
      l.actor.toLowerCase().includes(filterText.toLowerCase()) ||
      l.entity_type.toLowerCase().includes(filterText.toLowerCase()) ||
      (l.entity_id && l.entity_id.toLowerCase().includes(filterText.toLowerCase()))
  );

  return (
    <div className="space-y-4">
      {/* Top Banner */}
      <div className="bg-noc-surface border border-noc-border rounded-lg p-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <ShieldAlert className="w-5 h-5 text-noc-cyan" />
          <div>
            <div className="text-xs font-bold text-slate-100 flex items-center gap-2">
              <span>Immutable Governance & Audit Ledger</span>
              <Badge type="PUBLIC_SOURCE" label="TAMPER-EVIDENT UTC LOG" />
            </div>
            <div className="text-[11px] text-slate-400 font-mono">
              Traceable accountability for all external discovery, model forecasts, operator approvals, and TwinNode transfers.
            </div>
          </div>
        </div>

        <button
          onClick={loadLogs}
          disabled={isLoading}
          className="px-3 py-1.5 bg-noc-card hover:bg-noc-hover border border-noc-border rounded text-xs font-mono text-slate-200 flex items-center gap-1.5"
        >
          <RefreshCw className={`w-3.5 h-3.5 text-slate-400 ${isLoading ? 'animate-spin' : ''}`} />
          <span>Refresh Audit Trail</span>
        </button>
      </div>

      {/* Search & Audit Table */}
      <div className="grid grid-cols-12 gap-4">
        {/* Table of Events */}
        <div className="col-span-8 bg-noc-surface border border-noc-border rounded-lg p-4 space-y-3">
          <div className="flex items-center justify-between pb-2 border-b border-noc-border">
            <div className="flex items-center gap-2 flex-1 max-w-sm">
              <Search className="w-4 h-4 text-slate-500" />
              <input
                type="text"
                placeholder="Filter by action, actor, or entity..."
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                className="w-full bg-noc-card border border-noc-border rounded px-2.5 py-1 text-xs font-mono text-slate-200 focus:outline-none focus:border-noc-cyan"
              />
            </div>
            <span className="text-xs font-mono text-slate-400">Total Records: {filteredLogs.length}</span>
          </div>

          <div className="overflow-x-auto max-h-[550px] overflow-y-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead>
                <tr className="border-b border-noc-divider text-slate-500 text-[10px]">
                  <th className="py-2">TIMESTAMP (UTC)</th>
                  <th>ACTOR</th>
                  <th>ACTION</th>
                  <th>ENTITY</th>
                  <th>VERSION</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-noc-divider text-slate-300">
                {filteredLogs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="py-8 text-center text-slate-500">
                      No audit records found.
                    </td>
                  </tr>
                ) : (
                  filteredLogs.map((log) => {
                    const isSelected = selectedLog?.id === log.id;
                    return (
                      <tr
                        key={log.id}
                        onClick={() => setSelectedLog(log)}
                        className={`cursor-pointer transition ${
                          isSelected ? 'bg-noc-card text-noc-cyan' : 'hover:bg-noc-card/40'
                        }`}
                      >
                        <td className="py-2.5 text-slate-400 text-[10px]">
                          {log.timestamp.substring(11, 19)}
                        </td>
                        <td className="font-semibold text-slate-200 flex items-center gap-1.5">
                          <User className="w-3 h-3 text-slate-500" />
                          <span>{log.actor}</span>
                        </td>
                        <td className="text-noc-cyan">{log.action}</td>
                        <td className="text-slate-400 truncate max-w-[120px]">{log.entity_type}</td>
                        <td className="text-purple-300 font-bold">{log.state_version ?? '—'}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Selected Record Detail Drawer */}
        <div className="col-span-4 bg-noc-surface border border-noc-border rounded-lg p-4 flex flex-col justify-between overflow-y-auto h-[630px]">
          {selectedLog ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-noc-border">
                <span className="text-xs font-bold font-mono text-slate-200">Audit Record #{String(selectedLog.id).substring(0, 8)}</span>
                <Badge type="PUBLIC_SOURCE" label="LOG ENTRY" />
              </div>

              <div className="space-y-2 text-xs font-mono">
                <div>
                  <span className="text-slate-500 text-[10px] block">ACTION:</span>
                  <span className="text-noc-cyan font-bold">{selectedLog.action}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">ACTOR:</span>
                  <span className="text-slate-200">{selectedLog.actor}</span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">ENTITY:</span>
                  <span className="text-slate-200">
                    {selectedLog.entity_type} ({selectedLog.entity_id || 'N/A'})
                  </span>
                </div>
                <div>
                  <span className="text-slate-500 text-[10px] block">TIMESTAMP:</span>
                  <span className="text-slate-300">{selectedLog.timestamp}</span>
                </div>
              </div>

              <div>
                <span className="text-slate-400 text-xs font-semibold block mb-1">Payload Details:</span>
                <pre className="p-3 bg-noc-bg border border-noc-border rounded text-[11px] font-mono text-slate-300 overflow-x-auto max-h-72">
                  {JSON.stringify(selectedLog.details, null, 2)}
                </pre>
              </div>
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-xs text-slate-500 font-mono text-center">
              Select an audit record to inspect full JSON details and provenance.
            </div>
          )}

          <div className="pt-3 border-t border-noc-border text-[10px] font-mono text-slate-500 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>SQLite WAL-backed Append-Only Trail</span>
          </div>
        </div>
      </div>
    </div>
  );
};
