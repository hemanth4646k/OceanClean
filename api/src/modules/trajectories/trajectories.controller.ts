import {
  Controller,
  Get,
  Param,
  Patch,
  Post,
  UseGuards,
} from '@nestjs/common';
import { ApiBearerAuth, ApiOperation, ApiTags } from '@nestjs/swagger';
import { TrajectoriesService } from './trajectories.service';
import { JwtAuthGuard } from '../../common/guards/jwt-auth.guard';
import { RolesGuard } from '../../common/guards/roles.guard';
import { Roles } from '../../common/decorators/roles.decorator';

@ApiTags('Trajectory Optimization & Fleet Dispatch')
@Controller('trajectories')
export class TrajectoriesController {
  constructor(private readonly trajectoriesService: TrajectoriesService) {}

  @Post('generate')
  @UseGuards(JwtAuthGuard, RolesGuard)
  @Roles('FLEET_ADMIN')
  @ApiBearerAuth()
  @ApiOperation({
    summary:
      'Generate multi-vessel fuel-optimal interception routes using OR-Tools and ocean currents (Fleet Admin only)',
  })
  async generateRoutes() {
    return this.trajectoriesService.generateRoutes();
  }

  @Get()
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'List all planned or active interception routes' })
  async getAllRoutes() {
    return this.trajectoriesService.findAll();
  }

  @Get('analytics/hotspots')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary:
      'Proxy to Spark MLlib Gyre convergence hotspots computed over Parquet telemetry data lake',
  })
  async getHotspots() {
    return this.trajectoriesService.getAnalyticsHotspots();
  }

  @Get('currents-grid')
  @ApiOperation({
    summary: 'Get ocean current vector grid for WebGL particle streamlines',
  })
  async getCurrentsGrid() {
    return this.trajectoriesService.getCurrentsGrid();
  }

  @Get(':id')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({ summary: 'Get details and waypoints of a specific route' })
  async getRouteById(@Param('id') id: string) {
    return this.trajectoriesService.findById(id);
  }

  @Patch(':id/waypoints/:h3Index/complete')
  @UseGuards(JwtAuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary:
      'Vessel Captain marks an assigned H3 debris patch as harvested, updating load and patch status to CLEARED',
  })
  async completeWaypoint(
    @Param('id') id: string,
    @Param('h3Index') h3Index: string,
  ) {
    return this.trajectoriesService.completeWaypoint(id, h3Index);
  }
}

