import { useEffect, useState, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { SsePipelineEvent } from '../types/marine';

export function useSseTelemetry() {
  const [events, setEvents] = useState<SsePipelineEvent[]>([]);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [eventCount, setEventCount] = useState<number>(0);
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    const url = '/api/v1/telemetry/stream';
    let es: EventSource | null = null;

    try {
      es = new EventSource(url);
      eventSourceRef.current = es;

      es.onopen = () => {
        setIsConnected(true);
      };

      es.onmessage = (event) => {
        try {
          const parsed: SsePipelineEvent = JSON.parse(event.data);
          setEvents((prev) => [parsed, ...prev.slice(0, 99)]);
          setEventCount((c) => c + 1);

          // Trigger cache refetches based on pipeline stage
          if (parsed.stage === 'BAYESIAN_FUSION' || parsed.stage === 'KAFKA_INGEST') {
            queryClient.invalidateQueries({ queryKey: ['debris-patches'] });
          } else if (parsed.stage === 'ORTOOLS_ROUTE') {
            queryClient.invalidateQueries({ queryKey: ['trajectories'] });
            queryClient.invalidateQueries({ queryKey: ['debris-patches'] });
            queryClient.invalidateQueries({ queryKey: ['vessels'] });
          }
        } catch {
          // ignore non-json ping
        }
      };

      es.onerror = () => {
        setIsConnected(false);
      };
    } catch (e) {
      setIsConnected(false);
    }

    return () => {
      if (es) {
        es.close();
      }
    };
  }, [queryClient]);

  const clearLogs = () => setEvents([]);

  return {
    events,
    isConnected,
    eventCount,
    clearLogs,
  };
}

