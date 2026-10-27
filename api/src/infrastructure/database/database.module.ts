import { Global, Module, OnModuleInit, Logger } from '@nestjs/common';
import { db } from './index';
import { migrate } from 'drizzle-orm/node-postgres/migrator';
import * as path from 'path';

export const DRIZZLE_DB = 'DRIZZLE_DB';

@Global()
@Module({
  providers: [
    {
      provide: DRIZZLE_DB,
      useValue: db,
    },
  ],
  exports: [DRIZZLE_DB],
})
export class DatabaseModule implements OnModuleInit {
  private readonly logger = new Logger(DatabaseModule.name);

  async onModuleInit() {
    try {
      const migrationsFolder = path.resolve(process.cwd(), 'drizzle');
      await migrate(db, { migrationsFolder });
      this.logger.log('Database schema migrations verified/applied.');
    } catch (err: any) {
      this.logger.warn(`Database migration notice: ${err.message}`);
    }
  }
}

