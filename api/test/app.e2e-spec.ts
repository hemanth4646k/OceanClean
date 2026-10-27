import { INestApplication } from '@nestjs/common';
import { Test, TestingModule } from '@nestjs/testing';
import request from 'supertest';
import { AppModule } from '../src/app.module';
import { DRIZZLE_DB } from '../src/infrastructure/database/database.module';
import { KafkaService } from '../src/infrastructure/kafka/kafka.service';
import { users, vessels, debrisPatches, telemetryEvents, interceptionRoutes } from '../src/infrastructure/database/schema';

describe('Marine IoT API Gateway E2E Tests', () => {
  let app: INestApplication;
  let adminToken: string;
  const sensorKey = 'marine_sensor_key_secret_val_2026';

  // In-memory data store for E2E testing
  const store: Record<string, any[]> = {
    users: [],
    vessels: [],
    debrisPatches: [],
    telemetryEvents: [],
    interceptionRoutes: [],
  };

  const getTableStore = (table: any) => {
    if (table === users) return store.users;
    if (table === vessels) return store.vessels;
    if (table === debrisPatches) return store.debrisPatches;
    if (table === telemetryEvents) return store.telemetryEvents;
    if (table === interceptionRoutes) return store.interceptionRoutes;
    return [];
  };

  const mockDb = {
    select: () => ({
      from: (table: any) => {
        const tableData = getTableStore(table);
        const chain: any = {
          where: (predicate: any) => ({
            limit: (n: number) => tableData.slice(0, n),
            orderBy: () => [...tableData],
            then: (resolve: any) => resolve(tableData),
            [Symbol.iterator]: function* () {
              yield* tableData;
            },
          }),
          orderBy: () => [...tableData],
          then: (resolve: any) => resolve(tableData),
          [Symbol.iterator]: function* () {
            yield* tableData;
          },
        };
        return chain;
      },
    }),
    insert: (table: any) => ({
      values: (val: any) => ({
        returning: () => {
          const tableData = getTableStore(table);
          const item = {
            id: 'mock-uuid-' + (tableData.length + 1),
            ...val,
            createdAt: new Date(),
            updatedAt: new Date(),
            lastObservedAt: new Date(),
          };
          tableData.push(item);
          return [item];
        },
      }),
    }),
    update: (table: any) => ({
      set: (updateVal: any) => ({
        where: () => ({
          returning: () => {
            const tableData = getTableStore(table);
            if (tableData.length > 0) {
              Object.assign(tableData[0], updateVal);
              return [tableData[0]];
            }
            return [];
          },
        }),
      }),
    }),
  };

  const mockKafka = {
    sendTelemetryEvent: jest.fn().mockResolvedValue(undefined),
  };

  beforeAll(async () => {
    process.env.SENSOR_API_KEY = sensorKey;
    process.env.JWT_SECRET = 'super_secret_jwt_key_marine_clean_2026';

    const moduleFixture: TestingModule = await Test.createTestingModule({
      imports: [AppModule],
    })
      .overrideProvider(DRIZZLE_DB)
      .useValue(mockDb)
      .overrideProvider(KafkaService)
      .useValue(mockKafka)
      .compile();

    app = moduleFixture.createNestApplication();
    app.setGlobalPrefix('api/v1');
    await app.init();
  });

  afterAll(async () => {
    if (app) {
      await app.close();
    }
  });

  it('1. POST /api/v1/auth/register - Should register a new Fleet Admin', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/auth/register')
      .send({
        email: 'commander@oceanclean.org',
        password: 'Password123!',
        role: 'FLEET_ADMIN',
      })
      .expect(201);

    expect(res.body.user).toBeDefined();
    expect(res.body.user.email).toBe('commander@oceanclean.org');
    expect(res.body.accessToken).toBeDefined();
    adminToken = res.body.accessToken;
  });

  it('2. POST /api/v1/auth/login - Should login and acquire JWT', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/auth/login')
      .send({
        email: 'commander@oceanclean.org',
        password: 'Password123!',
      })
      .expect(200);

    expect(res.body.accessToken).toBeDefined();
  });

  it('3. GET /api/v1/auth/me - Should get profile with valid Bearer token', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/v1/auth/me')
      .set('Authorization', `Bearer ${adminToken}`)
      .expect(200);

    expect(res.body.email).toBe('commander@oceanclean.org');
    expect(res.body.role).toBe('FLEET_ADMIN');
  });

  it('4. POST /api/v1/telemetry/ingest - Should reject missing x-sensor-key (401)', async () => {
    await request(app.getHttpServer())
      .post('/api/v1/telemetry/ingest')
      .send({
        sourceTier: 'SATELLITE_SAR',
        sensorDeviceId: 'SAT-001',
        latitude: 28.5,
        longitude: -142.3,
        detectedDensityKgKm2: 25.0,
      })
      .expect(401);
  });

  it('5. POST /api/v1/telemetry/ingest - Should accept valid IoT telemetry with x-sensor-key', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/telemetry/ingest')
      .set('x-sensor-key', sensorKey)
      .send({
        sourceTier: 'SATELLITE_SAR',
        sensorDeviceId: 'SENTINEL-1-SAR',
        latitude: 28.5,
        longitude: -142.3,
        detectedDensityKgKm2: 30.0,
      })
      .expect(201);

    expect(res.body.h3Index).toBeDefined();
    expect(res.body.patch).toBeDefined();
    expect(res.body.patch.status).toBe('UNVERIFIED_ANOMALY');
  });

  it('6. POST /api/v1/telemetry/batch-sync - Should burst-sync buffered IoT array', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/telemetry/batch-sync')
      .set('x-sensor-key', sensorKey)
      .send({
        events: [
          {
            sourceTier: 'AERIAL_UAV',
            sensorDeviceId: 'UAV-SCAN-01',
            latitude: 28.5,
            longitude: -142.3,
            detectedDensityKgKm2: 45.0,
          },
        ],
      })
      .expect(200);

    expect(res.body.processedCount).toBe(1);
  });

  it('7. POST /api/v1/vessels - Fleet Admin creates cleanup ship', async () => {
    const res = await request(app.getHttpServer())
      .post('/api/v1/vessels')
      .set('Authorization', `Bearer ${adminToken}`)
      .send({
        name: 'Ocean Pioneer IV',
        callsign: 'OP-401',
        latitude: 26.0,
        longitude: -145.0,
        maxCapacityTons: 50.0,
        cruiseSpeedKnots: 14.0,
      })
      .expect(201);

    expect(res.body.name).toBe('Ocean Pioneer IV');
    expect(res.body.callsign).toBe('OP-401');
  });

  it('8. GET /api/v1/vessels - List all fleet vessels', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/v1/vessels')
      .set('Authorization', `Bearer ${adminToken}`)
      .expect(200);

    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
  });

  it('9. GET /api/v1/debris-patches - List active plastic patches', async () => {
    const res = await request(app.getHttpServer())
      .get('/api/v1/debris-patches')
      .set('Authorization', `Bearer ${adminToken}`)
      .expect(200);

    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThan(0);
  });
});

