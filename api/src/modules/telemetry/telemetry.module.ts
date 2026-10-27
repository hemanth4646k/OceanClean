import { Module, forwardRef } from '@nestjs/common';
import { TelemetryController } from './telemetry.controller';
import { TelemetryService } from './telemetry.service';
import { SimulationService } from './simulation.service';
import { DebrisPatchesModule } from '../debris-patches/debris-patches.module';
import { VesselsModule } from '../vessels/vessels.module';
import { TrajectoriesModule } from '../trajectories/trajectories.module';

@Module({
  imports: [
    DebrisPatchesModule,
    forwardRef(() => VesselsModule),
    forwardRef(() => TrajectoriesModule),
  ],
  controllers: [TelemetryController],
  providers: [TelemetryService, SimulationService],
  exports: [TelemetryService, SimulationService],
})
export class TelemetryModule {}
