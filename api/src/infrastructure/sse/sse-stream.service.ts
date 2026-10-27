import { Injectable, Logger, MessageEvent } from '@nestjs/common';
import { Observable, Subject } from 'rxjs';

export type PipelineStage =
  | 'KAFKA_INGEST'
  | 'BAYESIAN_FUSION'
  | 'OPEN_METEO_DRIFT'
  | 'SPARK_BATCH'
  | 'ORTOOLS_ROUTE';

export type PipelineLevel = 'INFO' | 'WARN' | 'SUCCESS';

export interface SsePipelineEvent {
  timestamp: string;
  stage: PipelineStage;
  level: PipelineLevel;
  message: string;
  payload?: any;
}

@Injectable()
export class SseStreamService {
  private readonly logger = new Logger(SseStreamService.name);
  private readonly eventSubject = new Subject<MessageEvent>();

  emit(event: {
    stage: PipelineStage;
    level?: PipelineLevel;
    message: string;
    payload?: any;
    timestamp?: string;
  }) {
    const fullEvent: SsePipelineEvent = {
      timestamp: event.timestamp || new Date().toISOString(),
      stage: event.stage,
      level: event.level || 'INFO',
      message: event.message,
      payload: event.payload,
    };

    this.logger.debug(`[SSE Stream] [${fullEvent.stage}] ${fullEvent.message}`);

    this.eventSubject.next({
      data: fullEvent,
    });
  }

  getStream(): Observable<MessageEvent> {
    return this.eventSubject.asObservable();
  }
}

