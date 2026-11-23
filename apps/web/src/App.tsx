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
      setSimState(msg.data);
    } else if (msg.event.startsWith('event.')) {
      refreshEvents();
    } else if (msg.event.startsWith('node.')) {
      refreshNodes();
    }
  }, []);

  const { isConnected: isWsConnected } = useLiveWebSocket(handleWsMessage);

  // Health check and primary initialization
  const initApp = async () => {
    try {
      const h = await api.getHealth();
      setHealth(h);
      setIsBackendConnected(true);

      // Load network cells and graph
      const cellData = await api.getCurrentCells();
      setCells(cellData.cells);

      const graph = await api.getCurrentGraph();
      setGraphData(graph);

      // Load or create initial simulation
      try {
        const sim = await api.createSimulation(42);
        setSimState(sim);
      } catch (_) {}

      // Load events
      const evList = await api.getEvents();
      setEvents(evList);
      if (evList.length > 0) {
        setSelectedEvent(evList[0]);
      }

      // Load nodes
      const nodeData = await api.getNodes();
      setNodes(nodeData);

      // Load plans
      const planData = await api.getPlans();
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
      if (evList.length > 0 && !selectedEvent) {
        setSelectedEvent(evList[0]);
      }
    } catch (_) {}
  };

  const refreshNodes = async () => {
    try {
      const nodeData = await api.getNodes();
      setNodes(nodeData);
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
      <ErrorBoundary fallbackScreen={() => setCurrentScreen('command')}>
        {currentScreen === 'command' && (
          <CommandCentre
            cells={cells}
            simState={simState}
            activeEvent={selectedEvent}
            nodes={nodes}
            onSelectScreen={setCurrentScreen}
            onSelectCell={setSelectedCellId}
          />
        )}

        {currentScreen === 'eventsense' && (
          <EventSense
            events={events}
            selectedEvent={selectedEvent}
            onSelectEvent={setSelectedEvent}
            onRefreshEvents={refreshEvents}
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
          />
        )}

        {currentScreen === 'audit' && (
          <GovernanceAudit />
        )}
      </ErrorBoundary>
    </Shell>
  );
};
