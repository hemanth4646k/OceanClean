import { Module } from '@nestjs/common';
import { TrajectoriesController } from './trajectories.controller';
import { TrajectoriesService } from './trajectories.service';
import { DebrisPatchesModule } from '../debris-patches/debris-patches.module';
import { VesselsModule } from '../vessels/vessels.module';

@Module({
  imports: [DebrisPatchesModule, VesselsModule],
  controllers: [TrajectoriesController],
  providers: [TrajectoriesService],
  exports: [TrajectoriesService],
})
export class TrajectoriesModule {}

