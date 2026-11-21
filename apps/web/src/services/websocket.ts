import { useEffect, useRef, useState, useCallback } from 'react';

export interface WebSocketMessage {
  event: string;
  timestamp: string;
  data: any;
}

export function useLiveWebSocket(onMessage?: (msg: WebSocketMessage) => void) {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const wsUrl = `${protocol}//${window.location.host}/ws/live`;
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setIsConnected(true);
        if (reconnectTimeoutRef.current) {
          clearTimeout(reconnectTimeoutRef.current);
          reconnectTimeoutRef.current = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const parsed: WebSocketMessage = JSON.parse(event.data);
          setLastMessage(parsed);
          if (onMessage) {
            onMessage(parsed);
          }
        } catch (_) {}
      };

      ws.onclose = () => {
        setIsConnected(false);
        // Auto-reconnect after 2.5s
        reconnectTimeoutRef.current = window.setTimeout(() => {
          connect();
        }, 2500);
      };

      ws.onerror = () => {
        ws.close();
      };

      wsRef.current = ws;
    } catch (_) {
      setIsConnected(false);
    }
  }, [onMessage]);

  useEffect(() => {
    connect();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  return { isConnected, lastMessage };
}
