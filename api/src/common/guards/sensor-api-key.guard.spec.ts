import { ExecutionContext, UnauthorizedException } from '@nestjs/common';
import { SensorApiKeyGuard } from './sensor-api-key.guard';

describe('SensorApiKeyGuard', () => {
  let guard: SensorApiKeyGuard;
  const validKey = 'marine_sensor_key_secret_val_2026';

  beforeEach(() => {
    process.env.SENSOR_API_KEY = validKey;
    guard = new SensorApiKeyGuard();
  });

  const createMockContext = (headerValue?: string): ExecutionContext => {
    return {
      switchToHttp: () => ({
        getRequest: () => ({
          headers: headerValue !== undefined ? { 'x-sensor-key': headerValue } : {},
        }),
      }),
    } as any;
  };

  it('should allow request when x-sensor-key is valid', () => {
    const ctx = createMockContext(validKey);
    expect(guard.canActivate(ctx)).toBe(true);
  });

  it('should throw UnauthorizedException when header is missing', () => {
    const ctx = createMockContext(undefined);
    expect(() => guard.canActivate(ctx)).toThrow(UnauthorizedException);
  });

  it('should throw UnauthorizedException when key length differs', () => {
    const ctx = createMockContext('short_key');
    expect(() => guard.canActivate(ctx)).toThrow(UnauthorizedException);
  });

  it('should throw UnauthorizedException when key content is wrong', () => {
    const wrongKey = validKey.slice(0, -1) + 'X';
    const ctx = createMockContext(wrongKey);
    expect(() => guard.canActivate(ctx)).toThrow(UnauthorizedException);
  });
});

