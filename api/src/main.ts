import { NestFactory } from '@nestjs/core';
import { AppModule } from './app.module';
import { DocumentBuilder, SwaggerModule } from '@nestjs/swagger';
import { Logger } from '@nestjs/common';

async function bootstrap() {
  const logger = new Logger('Bootstrap');
  const app = await NestFactory.create(AppModule);

  app.enableCors({
    origin: ['http://localhost:5173', 'http://localhost:8080', 'http://localhost:3000', '*'],
    methods: 'GET,HEAD,PUT,PATCH,POST,DELETE,OPTIONS',
    credentials: true,
  });
  app.setGlobalPrefix('api/v1');

  const config = new DocumentBuilder()
    .setTitle('Marine IoT Telemetry & Dynamic Trajectory Optimizer API')
    .setDescription(
      'Cloud-native backend API for multi-tier marine IoT telemetry ingestion, Bayesian sensor fusion, vessel tracking, and plastic interception routing',
    )
    .setVersion('1.0.0')
    .addBearerAuth()
    .addApiKey(
      { type: 'apiKey', name: 'x-sensor-key', in: 'header' },
      'x-sensor-key',
    )
    .build();

  const document = SwaggerModule.createDocument(app, config);
  SwaggerModule.setup('docs', app, document);

  // Health check endpoint for Docker and orchestration
  const httpAdapter = app.getHttpAdapter();
  httpAdapter.get('/health', (req: any, res: any) => {
    res.status(200).json({ status: 'ok', uptime: process.uptime() });
  });

  // Serve raw JSON OpenAPI at /docs-json as referenced in spec
  httpAdapter.get('/docs-json', (req: any, res: any) => {
    res.json(document);
  });

  const port = process.env.PORT || 3000;
  await app.listen(port);
  logger.log(`Marine IoT API listening on http://localhost:${port}/api/v1`);
  logger.log(`Swagger documentation available at http://localhost:${port}/docs`);
}

bootstrap();

