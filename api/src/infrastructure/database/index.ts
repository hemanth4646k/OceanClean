import { drizzle } from 'drizzle-orm/node-postgres';
import { Pool } from 'pg';
import * as schema from './schema';
import * as dotenv from 'dotenv';

dotenv.config();

const connectionString =
  process.env.DATABASE_URL ||
  'postgresql://ocean_admin:ocean_secure_password@localhost:5432/oceanclean_db';

export const pool = new Pool({
  connectionString,
});

export const db = drizzle(pool, { schema });
export type Database = typeof db;

