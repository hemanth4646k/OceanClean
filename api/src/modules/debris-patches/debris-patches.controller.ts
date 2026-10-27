import {
  Controller,
  Get,
  Param,
  Query,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiQuery, ApiTags } from '@nestjs/swagger';
import { DebrisPatchesService } from './debris-patches.service';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';

@ApiTags('Debris Patches')
@Controller('debris-patches')
export class DebrisPatchesController {
  constructor(private readonly debrisPatchesService: DebrisPatchesService) {}

  @Get()
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary: 'List all ocean plastic debris accumulation patches with optional status filtering',
  })
  @ApiQuery({
    name: 'status',
    required: false,
    enum: ['UNVERIFIED_ANOMALY', 'CONFIRMED_PATCH', 'INTERCEPT_ASSIGNED', 'CLEARED'],
  })
  async getAllPatches(@Query('status') status?: string) {
    return this.debrisPatchesService.findAll(status);
  }

  @Get(':id')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Get details of a specific debris patch by UUID' })
  async getPatchById(@Param('id') id: string) {
    return this.debrisPatchesService.findById(id);
  }
}

