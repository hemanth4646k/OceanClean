import { Module } from '@nestjs/common';
import { DebrisPatchesService } from './debris-patches.service';
import { DebrisPatchesController } from './debris-patches.controller';

@Module({
  controllers: [DebrisPatchesController],
  providers: [DebrisPatchesService],
  exports: [DebrisPatchesService],
})
export class DebrisPatchesModule {}

