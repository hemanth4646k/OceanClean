import { TelemetryService } from './telemetry.service';
import { latLngToCell } from 'h3-js';

describe('TelemetryService', () => {
  let service: TelemetryService;
  let mockDb: any;
  let mockKafkaService: any;
  let mockDebrisPatchesService: any;

  beforeEach(() => {
    mockDb = {
      insert: jest.fn().mockReturnValue({
        values: jest.fn().mockReturnValue({
          returning: jest.fn().mockResolvedValue([
            {
              id: 'event-uuid-1',
              sourceTier: 'SATELLITE_SAR',
              h3Index: '87283472bffffff',
              latitude: 30.0,
              longitude: -145.0,
              detectedDensityKgKm2: 20.0,
              rawConfidence: 0.55,
              seaStateWaveM: 1.5,
              observedAt: new Date(),
            },
          ]),
        }),
      }),
    };

    mockKafkaService = {
      sendTelemetryEvent: jest.fn().mockResolvedValue(undefined),
    };

    mockDebrisPatchesService = {
      fuseTelemetry: jest.fn().mockResolvedValue({
        id: 'patch-uuid-1',
        status: 'UNVERIFIED_ANOMALY',
        confidenceScore: 0.55,
        polymerDensityKgKm2: 20.0,
        estimatedMassKg: 103.2,
      }),
    };

    service = new TelemetryService(
      mockDb,
      mockKafkaService,
      mockDebrisPatchesService,
    );
  });

  it('should compute valid H3 resolution 7 cell and dispatch event to DB, Fusion, and Kafka', async () => {
    const lat = 32.1234;
    const lon = -140.5678;
    const expectedH3 = latLngToCell(lat, lon, 7);

    const result = await service.processEvent({
      sourceTier: 'SATELLITE_SAR',
      sensorDeviceId: 'SENTINEL-1-SAR-001',
      latitude: lat,
      longitude: lon,
      detectedDensityKgKm2: 20.0,
      seaStateWaveM: 1.0,
    });

    expect(result.h3Index).toBe(expectedH3);
    expect(mockDebrisPatchesService.fuseTelemetry).toHaveBeenCalledWith(
      expect.objectContaining({
        h3Index: expectedH3,
        sourceTier: 'SATELLITE_SAR',
      }),
    );
    expect(mockKafkaService.sendTelemetryEvent).toHaveBeenCalled();
  });

  it('should process batch sync for disconnected sea edge reconnect', async () => {
    const events = [
      {
        sourceTier: 'VESSEL_OPTICAL' as const,
        sensorDeviceId: 'VESSEL-CAM-01',
        latitude: 31.0,
        longitude: -141.0,
        detectedDensityKgKm2: 40.0,
        seaStateWaveM: 1.2,
      },
      {
        sourceTier: 'DRIFT_BUOY' as const,
        sensorDeviceId: 'BUOY-4402',
        latitude: 31.2,
        longitude: -141.2,
        detectedDensityKgKm2: 38.0,
        seaStateWaveM: 1.5,
      },
    ];

    const batchResult = await service.processBatch(events);
    expect(batchResult.processedCount).toBe(2);
    expect(batchResult.events.length).toBe(2);
  });
});

