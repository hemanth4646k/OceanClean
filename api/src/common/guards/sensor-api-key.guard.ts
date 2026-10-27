import {
  CanActivate,
  ExecutionContext,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import * as crypto from 'crypto';

@Injectable()
export class SensorApiKeyGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const request = context.switchToHttp().getRequest();
    const providedKey = request.headers['x-sensor-key'];

    if (!providedKey || typeof providedKey !== 'string') {
      throw new UnauthorizedException('Missing x-sensor-key header');
    }

    const expectedKey =
      process.env.SENSOR_API_KEY || 'marine_sensor_key_secret_val_2026';

    const providedBuffer = Buffer.from(providedKey);
    const expectedBuffer = Buffer.from(expectedKey);

    if (providedBuffer.length !== expectedBuffer.length) {
      throw new UnauthorizedException('Invalid x-sensor-key');
    }

    const isValid = crypto.timingSafeEqual(providedBuffer, expectedBuffer);
    if (!isValid) {
      throw new UnauthorizedException('Invalid x-sensor-key');
    }

    return true;
  }
}

