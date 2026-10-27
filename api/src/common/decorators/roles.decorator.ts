import { SetMetadata } from '@nestjs/common';

export const ROLES_KEY = 'roles';
export const Roles = (...roles: Array<'FLEET_ADMIN' | 'VESSEL_CAPTAIN'>) =>
  SetMetadata(ROLES_KEY, roles);

