import {
  BadRequestException,
  Body,
  Controller,
  Get,
  Param,
  Patch,
  PipeTransform,
  Post,
  UseGuards,
  UsePipes,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { ZodSchema } from 'zod';
import { VesselsService } from './vessels.service';
import {
  CreateVesselDto,
  CreateVesselSchema,
  UpdateVesselTelemetryDto,
  UpdateVesselTelemetrySchema,
} from './dto/vessels.dto';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { Roles } from '../../common/decorators/roles.decorator';

class ZodValidationPipe implements PipeTransform {
  constructor(private schema: ZodSchema<any>) {}
  transform(value: any) {
    const result = this.schema.safeParse(value);
    if (!result.success) {
      throw new BadRequestException(result.error.errors);
    }
    return result.data;
  }
}

@ApiTags('Fleet Vessels')
@Controller('vessels')
export class VesselsController {
  constructor(private readonly vesselsService: VesselsService) {}

  @Post()
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('FLEET_ADMIN')
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Register a new cleanup vessel (Admin only)' })
  @UsePipes(new ZodValidationPipe(CreateVesselSchema))
  async createVessel(@Body() dto: CreateVesselDto) {
    return this.vesselsService.create(dto);
  }

  @Get()
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'List all cleanup vessels in fleet' })
  async getAllVessels() {
    return this.vesselsService.findAll();
  }

  @Get(':id')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Get details of a specific vessel' })
  async getVessel(@Param('id') id: string) {
    return this.vesselsService.findById(id);
  }

  @Patch(':id/telemetry')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Update vessel position, heading, fuel and load status' })
  @UsePipes(new ZodValidationPipe(UpdateVesselTelemetrySchema))
  async updateTelemetry(
    @Param('id') id: string,
    @Body() dto: UpdateVesselTelemetryDto,
  ) {
    return this.vesselsService.updateTelemetry(id, dto);
  }
}

