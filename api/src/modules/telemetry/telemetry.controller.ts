import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpCode,
  HttpStatus,
  MessageEvent,
  PipeTransform,
  Post,
  Sse,
  UseGuards,
  UsePipes,
} from '@nestjs/common';
import { ApiHeader, ApiOperation, ApiTags } from '@nestjs/swagger';
import { Observable } from 'rxjs';
import { ZodSchema } from 'zod';
import { SensorApiKeyGuard } from '../../common/guards/sensor-api-key.guard';
import { SseStreamService } from '../../infrastructure/sse/sse-stream.service';
import { TelemetryService } from './telemetry.service';
import { SimulationService, SimulateScenarioDto } from './simulation.service';
import {
  TelemetryBatchSyncDto,
  TelemetryBatchSyncSchema,
  TelemetryIngestDto,
  TelemetryIngestSchema,
} from './dto/telemetry.dto';

class ZodValidationPipe implements PipeTransform {
  constructor(private schema: ZodSchema<any>) {}
  transform(value: any) {
    const result = this.schema.safeParse(value);
    if (!result.success) {
      throw new BadRequestException(result.error.errors);
    }
    return result.data;
  }
}

@ApiTags('Telemetry Ingestion & Simulation')
@Controller('telemetry')
export class TelemetryController {
  constructor(
    private readonly telemetryService: TelemetryService,
    private readonly sseStreamService: SseStreamService,
    private readonly simulationService: SimulationService,
  ) {}

  @Sse('stream')
  @ApiOperation({
    summary: 'Server-Sent Events (SSE) telemetry and pipeline status stream',
  })
  streamTelemetry(): Observable<MessageEvent> {
    return this.sseStreamService.getStream();
  }

  @Post('ingest')
  @UseGuards(SensorApiKeyGuard)
  @ApiHeader({
    name: 'x-sensor-key',
    description: 'Secret pre-shared sensor authentication key',
    required: true,
  })
  @ApiOperation({
    summary:
      'Ingest real-time marine IoT telemetry event (Satellite, UAV, Vessel, Buoy)',
  })
  @UsePipes(new ZodValidationPipe(TelemetryIngestSchema))
  async ingestTelemetry(@Body() dto: TelemetryIngestDto) {
    return this.telemetryService.processEvent(dto);
  }

  @Post('batch-sync')
  @HttpCode(HttpStatus.OK)
  @UseGuards(SensorApiKeyGuard)
  @ApiHeader({
    name: 'x-sensor-key',
    description: 'Secret pre-shared sensor authentication key',
    required: true,
  })
  @ApiOperation({
    summary:
      'Burst-upload buffered telemetry array when vessels reconnect after disconnected sea operations',
  })
  @UsePipes(new ZodValidationPipe(TelemetryBatchSyncSchema))
  async batchSyncTelemetry(@Body() dto: TelemetryBatchSyncDto) {
    return this.telemetryService.processBatch(dto.events);
  }

  @Post('simulate-scenario')
  @HttpCode(HttpStatus.CREATED)
  @ApiOperation({
    summary:
      'Trigger 1-click cloud simulation scenario (SAR Sweep, UAV Recon, Edge Burst, Storm Chaos)',
  })
  async simulateScenario(@Body() dto: SimulateScenarioDto) {
    return this.simulationService.runScenario(dto);
  }
}
