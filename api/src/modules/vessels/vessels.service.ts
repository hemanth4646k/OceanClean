import {
  ConflictException,
  Inject,
  Injectable,
  NotFoundException,
} from '@nestjs/common';
import { eq } from 'drizzle-orm';
import { latLngToCell } from 'h3-js';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import { vessels, Vessel } from '../../infrastructure/database/schema';
import { CreateVesselDto, UpdateVesselTelemetryDto } from './dto/vessels.dto';

@Injectable()
export class VesselsService {
  constructor(@Inject(DRIZZLE_DB) private readonly db: Database) {}

  async create(dto: CreateVesselDto): Promise<Vessel> {
    const existing = await this.db
      .select()
      .from(vessels)
      .where(eq(vessels.callsign, dto.callsign));

    if (existing.length > 0) {
      throw new ConflictException(
        `Vessel with callsign ${dto.callsign} already exists`,
      );
    }

    const h3Index = latLngToCell(dto.latitude, dto.longitude, 7);

    const [newVessel] = await this.db
      .insert(vessels)
      .values({
        name: dto.name,
        callsign: dto.callsign,
        operatorId: dto.operatorId,
        status: dto.status ?? 'IDLE',
        latitude: dto.latitude,
        longitude: dto.longitude,
        h3Index,
        maxCapacityTons: dto.maxCapacityTons,
        currentLoadTons: dto.currentLoadTons ?? 0,
        fuelLevelPct: dto.fuelLevelPct ?? 100,
        cruiseSpeedKnots: dto.cruiseSpeedKnots ?? 12,
        updatedAt: new Date(),
      })
      .returning();

    return newVessel;
  }

  async findAll(): Promise<Vessel[]> {
    return this.db.select().from(vessels);
  }

  async findById(id: string): Promise<Vessel> {
    const [vessel] = await this.db
      .select()
      .from(vessels)
      .where(eq(vessels.id, id));

    if (!vessel) {
      throw new NotFoundException(`Vessel with id ${id} not found`);
    }
    return vessel;
  }

  async updateTelemetry(id: string, dto: UpdateVesselTelemetryDto): Promise<Vessel> {
    const vessel = await this.findById(id);
    const h3Index = latLngToCell(dto.latitude, dto.longitude, 7);

    const [updated] = await this.db
      .update(vessels)
      .set({
        latitude: dto.latitude,
        longitude: dto.longitude,
        h3Index,
        ...(dto.status && { status: dto.status }),
        ...(dto.currentLoadTons !== undefined && { currentLoadTons: dto.currentLoadTons }),
        ...(dto.fuelLevelPct !== undefined && { fuelLevelPct: dto.fuelLevelPct }),
        ...(dto.cruiseSpeedKnots !== undefined && { cruiseSpeedKnots: dto.cruiseSpeedKnots }),
        updatedAt: new Date(),
      })
      .where(eq(vessels.id, vessel.id))
      .returning();

    return updated;
  }

  async incrementLoad(id: string, additionalTons: number): Promise<Vessel> {
    const vessel = await this.findById(id);
    const newLoad = vessel.currentLoadTons + additionalTons;

    const [updated] = await this.db
      .update(vessels)
      .set({
        currentLoadTons: newLoad,
        updatedAt: new Date(),
      })
      .where(eq(vessels.id, vessel.id))
      .returning();

    return updated;
  }
}

