import React, { useState, useEffect, useCallback } from 'react';
import { Shell, ScreenId } from './components/layout/Shell';
import { CommandCentre } from './pages/CommandCentre';
import { EventSense } from './pages/EventSense';
import { NetworkTwin } from './pages/NetworkTwin';
import { PredictionOrchestration } from './pages/PredictionOrchestration';
import { TwinNodeLab } from './pages/TwinNodeLab';
import { Verification } from './pages/Verification';
import { GovernanceAudit } from './pages/GovernanceAudit';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { api } from './services/api';
import { useLiveWebSocket, WebSocketMessage } from './services/websocket';
import {
  CellRecord,
  EventRecord,
  GraphResponse,
  HealthResponse,
  NodeRecord,
  PlanRecord,
  SimulationStateResponse,
} from './types/api';

export const App: React.FC = () => {
  const [currentScreen, setCurrentScreen] = useState<ScreenId>('command');
  const [isBackendConnected, setIsBackendConnected] = useState<boolean>(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);

  // Core Data
  const [cells, setCells] = useState<CellRecord[]>([]);
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [simState, setSimState] = useState<SimulationStateResponse | null>(null);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<EventRecord | null>(null);
  const [selectedCellId, setSelectedCellId] = useState<string | null>('CELL-BLR-018');
  const [nodes, setNodes] = useState<NodeRecord[]>([]);
  const [plans, setPlans] = useState<PlanRecord[]>([]);
  const [isResetting, setIsResetting] = useState<boolean>(false);

  // WebSocket message handler
  const handleWsMessage = useCallback((msg: WebSocketMessage) => {
    if (msg.event === 'tick.updated' && msg.data) {
      if (Array.isArray(msg.data.telemetry) && msg.data.telemetry.length > 0 && msg.data.sim_time_utc) {
        setSimState(msg.data);
      } else {
        // Retain existing telemetry array and sim_time_utc if WS broadcast only transmits delta/summary
        setSimState((prev) =>
          prev
            ? {
                ...prev,
                ...msg.data,
                telemetry: prev.telemetry || [],
                sim_time_utc: msg.data.sim_time_utc || prev.sim_time_utc,
              }
            : null
        );
      }
    } else if (msg.event.startsWith('event.')) {
      refreshEvents();
    } else if (msg.event.startsWith('node.')) {
      refreshNodes();
    } else if (msg.event.startsWith('plan.')) {
      refreshPlans();
    }
  }, []);

  const { isConnected: isWsConnected } = useLiveWebSocket(handleWsMessage);

  // Health check and primary initialization
  const initApp = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      setIsBackendConnected(true);

      // Load remaining dashboard state in parallel so simState is ready immediately
      const [cellData, graph, sim, evList, nodeData, planData] = await Promise.all([
        api.getCurrentCells(),
        api.getCurrentGraph(),
        api.createSimulation(42).catch(() => null),
        api.getEvents(),
        api.getNodes(),
        api.getPlans(),
      ]);

      setCells(cellData.cells);
      setGraphData(graph);
      if (sim) setSimState(sim);
      setEvents(evList);
      if (evList.length > 0) {
        setSelectedEvent(evList[0]);
      }
      setNodes(nodeData);
      setPlans(planData);
    } catch (_) {
      setIsBackendConnected(false);
    }
  };

  useEffect(() => {
    initApp();
    const interval = setInterval(async () => {
      try {
        const h = await api.getHealth();
        setHealth(h);
        setIsBackendConnected(true);
      } catch (_) {
        setIsBackendConnected(false);
      }
    }, 4000);
    return () => clearInterval(interval);
  }, []);

  const refreshEvents = async () => {
    try {
      const evList = await api.getEvents();
      setEvents(evList);
      setSelectedEvent((prev) => {
        if (prev) {
          const updated = evList.find((e) => e.event_id === prev.event_id);
          if (updated) return updated;
        }
        return evList.length > 0 ? evList[0] : prev;
      });
    } catch (_) {}
  };

  const refreshNodes = async () => {
    try {
      const nodeData = await api.getNodes();
      setNodes(nodeData);
    } catch (_) {}
  };

  const refreshPlans = async (simId?: string) => {
    try {
      const targetSimId = simId || simState?.simulation_id;
      const planData = await api.getPlans(targetSimId);
      setPlans(planData);
    } catch (_) {}
  };

  const refreshSimulation = async () => {
    if (!simState) return;
    try {
      const s = await api.getSimulationState(simState.simulation_id);
      setSimState(s);
      const planData = await api.getPlans(simState.simulation_id);
      setPlans(planData);
    } catch (_) {}
  };

  // Reset Demo handler
  const handleResetDemo = async () => {
    setIsResetting(true);
    try {
      await api.seedNetwork(42, 100);
      const newSim = await api.createSimulation(42);
      setSimState(newSim);
      await refreshEvents();
      await refreshNodes();
      await refreshPlans(newSim.simulation_id);
      const cellData = await api.getCurrentCells();
      setCells(cellData.cells);
      const graph = await api.getCurrentGraph();
      setGraphData(graph);
    } catch (_) {
    } finally {
      setIsResetting(false);
    }
  };

  return (
    <Shell
      currentScreen={currentScreen}
      onSelectScreen={setCurrentScreen}
      isBackendConnected={isBackendConnected}
      isWsConnected={isWsConnected}
      tick={simState?.tick || 0}
      simTime={simState?.sim_time_utc || '2026-11-21T12:00:00Z'}
      seed={simState?.seed || 42}
      runId={simState?.simulation_id || null}
      onResetDemo={handleResetDemo}
      isResetting={isResetting}
    >
      <ErrorBoundary key={currentScreen} fallbackScreen={() => setCurrentScreen('command')}>
        {currentScreen === 'command' && (
          <CommandCentre
            cells={cells}
            simState={simState}
            activeEvent={selectedEvent}
            nodes={nodes}
            onSelectScreen={setCurrentScreen}
            onSelectCell={setSelectedCellId}
            onRefreshSimulation={refreshSimulation}
            onRefreshEvents={refreshEvents}
          />
        )}

        {currentScreen === 'eventsense' && (
          <EventSense
            events={events}
            selectedEvent={selectedEvent}
            onSelectEvent={setSelectedEvent}
            onRefreshEvents={refreshEvents}
            onRefreshSimulation={refreshSimulation}
            activeSimulationId={simState?.simulation_id || null}
          />
        )}

        {currentScreen === 'twin' && (
          <NetworkTwin
            cells={cells}
            graphData={graphData}
            simState={simState}
            selectedCellId={selectedCellId}
            onSelectCell={setSelectedCellId}
            onRefreshSimulation={refreshSimulation}
          />
        )}

        {currentScreen === 'prediction' && (
          <PredictionOrchestration
            cells={cells}
            simState={simState}
            selectedCellId={selectedCellId}
            onSelectCell={setSelectedCellId}
            onRefreshSimulation={refreshSimulation}
            onRefreshPlans={() => refreshPlans(simState?.simulation_id)}
            onSelectScreen={setCurrentScreen}
          />
        )}

        {currentScreen === 'twinnode' && (
          <TwinNodeLab
            nodes={nodes}
            onRefreshNodes={refreshNodes}
          />
        )}

        {currentScreen === 'verification' && (
          <Verification
            simState={simState}
            plans={plans}
            onRefreshPlans={() => refreshPlans(simState?.simulation_id)}
          />
        )}

        {currentScreen === 'audit' && (
          <GovernanceAudit />
        )}
      </ErrorBoundary>
    </Shell>
  );
};
