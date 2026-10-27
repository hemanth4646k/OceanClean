import { Module } from '@nestjs/common';
import { DatabaseModule } from './infrastructure/database/database.module';
import { KafkaModule } from './infrastructure/kafka/kafka.module';
import { SseModule } from './infrastructure/sse/sse.module';
import { AuthModule } from './modules/auth/auth.module';
import { DebrisPatchesModule } from './modules/debris-patches/debris-patches.module';
import { TelemetryModule } from './modules/telemetry/telemetry.module';
import { VesselsModule } from './modules/vessels/vessels.module';
import { TrajectoriesModule } from './modules/trajectories/trajectories.module';

@Module({
  imports: [
    DatabaseModule,
    KafkaModule,
    SseModule,
    AuthModule,
    DebrisPatchesModule,
    TelemetryModule,
    VesselsModule,
    TrajectoriesModule,
  ],
})
export class AppModule {}

