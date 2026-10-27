import { DebrisPatchesService } from './debris-patches.service';

describe('DebrisPatchesService - Bayesian Confidence Fusion', () => {
  let service: DebrisPatchesService;
  let mockDb: any;
  let inMemoryPatches: any[] = [];

  beforeEach(() => {
    inMemoryPatches = [];

    mockDb = {
      select: jest.fn().mockReturnValue({
        from: jest.fn().mockReturnValue({
          where: jest.fn().mockImplementation(() => {
            return {
              limit: jest.fn().mockImplementation((limitNum: number) => {
                return inMemoryPatches.slice(0, limitNum);
              }),
              orderBy: jest.fn().mockReturnValue(inMemoryPatches),
            };
          }),
          orderBy: jest.fn().mockReturnValue(inMemoryPatches),
        }),
      }),
      insert: jest.fn().mockReturnValue({
        values: jest.fn().mockImplementation((val: any) => ({
          returning: jest.fn().mockImplementation(() => {
            const created = {
              id: 'mock-uuid-' + (inMemoryPatches.length + 1),
              ...val,
              createdAt: new Date(),
            };
            inMemoryPatches.push(created);
            return [created];
          }),
        })),
      }),
      update: jest.fn().mockReturnValue({
        set: jest.fn().mockImplementation((updateVals: any) => ({
          where: jest.fn().mockImplementation(() => ({
            returning: jest.fn().mockImplementation(() => {
              if (inMemoryPatches.length > 0) {
                Object.assign(inMemoryPatches[0], updateVals);
                return [inMemoryPatches[0]];
              }
              return [];
            }),
          })),
        })),
      }),
    };

    service = new DebrisPatchesService(mockDb);
  });

  it('should calculate correct log-odds Bayesian confidence updates', () => {
    // Satellite SAR prior = 0.55
    const prior = 0.55;
    // Aerial UAV weight = 0.85
    const uavWeight = 0.85;

    const updated = service.calculateBayesianUpdate(prior, uavWeight);
    // (0.55 * 0.85) / (0.55 * 0.85 + (1 - 0.55) * (1 - 0.85)) = 0.4675 / (0.4675 + 0.0675) = 0.8738
    expect(updated).toBeGreaterThanOrEqual(0.8);
    expect(updated).toBeCloseTo(0.8738, 2);
  });

  it('should create an UNVERIFIED_ANOMALY (0.55) on SATELLITE_SAR and promote to CONFIRMED_PATCH (>= 0.80) on AERIAL_UAV', async () => {
    const h3Cell = '87283472bffffff';
    const lat = 28.5;
    const lon = -142.3;

    // Step 1: Satellite SAR ping
    const firstPing = await service.fuseTelemetry({
      sourceTier: 'SATELLITE_SAR',
      h3Index: h3Cell,
      latitude: lat,
      longitude: lon,
      detectedDensityKgKm2: 15.0,
    });

    expect(firstPing).toBeDefined();
    expect(firstPing.status).toBe('UNVERIFIED_ANOMALY');
    expect(firstPing.confidenceScore).toBe(0.55);
    expect(firstPing.h3Index).toBe(h3Cell);

    // Step 2: Aerial UAV sweep arrives in same H3 cell
    const secondPing = await service.fuseTelemetry({
      sourceTier: 'AERIAL_UAV',
      h3Index: h3Cell,
      latitude: lat,
      longitude: lon,
      detectedDensityKgKm2: 25.0,
    });

    expect(secondPing).toBeDefined();
    expect(secondPing.confidenceScore).toBeGreaterThanOrEqual(0.8);
    expect(secondPing.status).toBe('CONFIRMED_PATCH');
  });

  it('should further boost confidence to > 0.95 when confirmed by VESSEL_OPTICAL', async () => {
    const prior = 0.8738;
    const opticalWeight = 0.95;
    const thirdUpdate = service.calculateBayesianUpdate(prior, opticalWeight);
    expect(thirdUpdate).toBeGreaterThan(0.95);
  });
});

