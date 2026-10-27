import { Injectable, Logger, OnModuleDestroy, OnModuleInit } from '@nestjs/common';
import { Kafka, Producer } from 'kafkajs';

@Injectable()
export class KafkaService implements OnModuleInit, OnModuleDestroy {
  private readonly logger = new Logger(KafkaService.name);
  private kafka: Kafka | null = null;
  private producer: Producer | null = null;
  private isConnected = false;

  onModuleInit() {
    const brokers = (process.env.KAFKA_BROKERS || 'localhost:9092').split(',');
    try {
      this.kafka = new Kafka({
        clientId: 'marine-api-gateway',
        brokers,
        retry: {
          initialRetryTime: 300,
          retries: 3,
        },
      });
      this.producer = this.kafka.producer();
      this.producer
        .connect()
        .then(() => {
          this.isConnected = true;
          this.logger.log(`Connected to Kafka brokers at: ${brokers.join(', ')}`);
        })
        .catch((err) => {
          this.logger.warn(`Kafka broker not immediately reachable: ${err.message}. Messages will be safely buffered/logged.`);
        });
    } catch (e: any) {
      this.logger.warn(`Failed to initialize Kafka client: ${e.message}`);
    }
  }

  async sendTelemetryEvent(topic: string, key: string, payload: any): Promise<void> {
    const messageValue = JSON.stringify(payload);
    if (this.producer && this.isConnected) {
      try {
        await this.producer.send({
          topic,
          messages: [{ key, value: messageValue }],
        });
        return;
      } catch (err: any) {
        this.logger.warn(`Failed to publish message to Kafka [${topic}]: ${err.message}`);
      }
    } else {
      this.logger.debug(`[Kafka Offline Fallback] Topic: ${topic}, Key: ${key}`);
    }
  }

  async onModuleDestroy() {
    if (this.producer && this.isConnected) {
      await this.producer.disconnect();
    }
  }
}

