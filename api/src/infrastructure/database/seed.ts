import * as bcrypt from 'bcryptjs';
import { latLngToCell } from 'h3-js';
import { db, pool } from './index';
import {
  users,
  vessels,
  debrisPatches,
  interceptionRoutes,
} from './schema';

export async function runDatabaseSeed() {
  console.log('🌊 Seeding Marine IoT Database with Gyre Demo State...');

  // 1. Operators
  const passwordHash = bcrypt.hashSync('Password123!', 10);
  const [adminUser] = await db
    .insert(users)
    .values({
      email: 'commander@oceanclean.org',
      passwordHash,
      role: 'FLEET_ADMIN',
    })
    .onConflictDoNothing()
    .returning();

  const [captainUser] = await db
    .insert(users)
    .values({
      email: 'captain.sarah@oceanclean.org',
      passwordHash,
      role: 'VESSEL_CAPTAIN',
    })
    .onConflictDoNothing()
    .returning();

  const operatorId = captainUser?.id || adminUser?.id;

  // 2. 4 Fleet Vessels
  const vesselSeeds = [
    {
      name: 'RV Ocean Interceptor',
      callsign: 'OI-101',
      latitude: 28.5,
      longitude: -146.0,
      maxCapacityTons: 60.0,
      currentLoadTons: 12.5,
      fuelLevelPct: 88.0,
      cruiseSpeedKnots: 14.0,
      status: 'HARVESTING' as const,
    },
    {
      name: 'ASV Pacific Vanguard',
      callsign: 'PV-202',
      latitude: 32.0,
      longitude: -142.5,
      maxCapacityTons: 40.0,
      currentLoadTons: 4.0,
      fuelLevelPct: 92.0,
      cruiseSpeedKnots: 12.0,
      status: 'EN_ROUTE' as const,
    },
    {
      name: 'RV Gyre Harvester',
      callsign: 'GH-303',
      latitude: 30.5,
      longitude: -148.5,
      maxCapacityTons: 80.0,
      currentLoadTons: 0.0,
      fuelLevelPct: 95.0,
      cruiseSpeedKnots: 13.0,
      status: 'IDLE' as const,
    },
    {
      name: 'ASV Albatross',
      callsign: 'AL-404',
      latitude: 34.0,
      longitude: -144.0,
      maxCapacityTons: 25.0,
      currentLoadTons: 0.0,
      fuelLevelPct: 100.0,
      cruiseSpeedKnots: 16.0,
      status: 'IDLE' as const,
    },
  ];

  const createdVessels: any[] = [];
  for (const v of vesselSeeds) {
    const h3Index = latLngToCell(v.latitude, v.longitude, 7);
    const [inserted] = await db
      .insert(vessels)
      .values({
        ...v,
        h3Index,
        operatorId,
        updatedAt: new Date(),
      })
      .onConflictDoNothing()
      .returning();
    if (inserted) createdVessels.push(inserted);
  }

  // 3. 20 Initial Debris Patches
  const patchSeeds: any[] = [];
  for (let i = 0; i < 20; i++) {
    const lat = 27.0 + (i % 6) * 1.5 + (Math.random() * 0.4);
    const lon = -150.0 + Math.floor(i / 6) * 3.5 + (Math.random() * 0.5);
    const h3Index = latLngToCell(lat, lon, 7);
    const isConfirmed = i < 12;
    const isAssigned = i === 0 || i === 1;

    const density = 25.0 + i * 4.5;
    const massKg = density * 5.16;
    const confidence = isConfirmed ? 0.85 + (i * 0.01) : 0.55 + (i * 0.015);

    patchSeeds.push({
      h3Index,
      latitude: lat,
      longitude: lon,
      estimatedMassKg: massKg,
      polymerDensityKgKm2: density,
      confidenceScore: parseFloat(confidence.toFixed(2)),
      status: isAssigned
        ? ('INTERCEPT_ASSIGNED' as const)
        : isConfirmed
        ? ('CONFIRMED_PATCH' as const)
        : ('UNVERIFIED_ANOMALY' as const),
      currentVelocityMs: 1.2,
      currentDirectionDeg: 90.0,
      predictedLat6h: lat,
      predictedLon6h: lon + 0.35,
      lastObservedAt: new Date(),
    });
  }

  for (const p of patchSeeds) {
    await db.insert(debrisPatches).values(p).onConflictDoNothing();
  }

  // 4. Seed 2 Active Interception Routes if vessels were created
  if (createdVessels.length >= 2) {
    const v1 = createdVessels[0];
    const v2 = createdVessels[1];

    await db.insert(interceptionRoutes).values([
      {
        vesselId: v1.id,
        status: 'ACTIVE',
        totalDistanceNm: 42.5,
        estimatedFuelLiters: 580.0,
        expectedYieldKg: 14200.0,
        waypointsJson: [
          {
            patchId: 'patch-demo-1',
            h3Index: patchSeeds[0].h3Index,
            targetLatitude: patchSeeds[0].predictedLat6h,
            targetLongitude: patchSeeds[0].predictedLon6h,
            estimatedMassKg: patchSeeds[0].estimatedMassKg,
            distanceNm: 22.0,
            estimatedFuelLiters: 290.0,
            completed: false,
          },
        ],
        createdAt: new Date(),
      },
      {
        vesselId: v2.id,
        status: 'PLANNED',
        totalDistanceNm: 55.0,
        estimatedFuelLiters: 740.0,
        expectedYieldKg: 18500.0,
        waypointsJson: [
          {
            patchId: 'patch-demo-2',
            h3Index: patchSeeds[1].h3Index,
            targetLatitude: patchSeeds[1].predictedLat6h,
            targetLongitude: patchSeeds[1].predictedLon6h,
            estimatedMassKg: patchSeeds[1].estimatedMassKg,
            distanceNm: 28.0,
            estimatedFuelLiters: 370.0,
            completed: false,
          },
        ],
        createdAt: new Date(),
      },
    ]);
  }

  console.log('✅ Demo state successfully seeded!');
}

if (require.main === module) {
  runDatabaseSeed()
    .then(() => pool.end())
    .catch((err) => {
      console.error('Seed failed:', err);
      pool.end();
      process.exit(1);
    });
}
