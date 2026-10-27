import { Global, Module } from '@nestjs/common';
import { SseStreamService } from './sse-stream.service';

@Global()
@Module({
  providers: [SseStreamService],
  exports: [SseStreamService],
})
export class SseModule {}

