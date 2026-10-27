import {
  ConflictException,
  Inject,
  Injectable,
  UnauthorizedException,
} from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcryptjs';
import { eq } from 'drizzle-orm';
import { DRIZZLE_DB } from '../../infrastructure/database/database.module';
import { Database } from '../../infrastructure/database';
import { users } from '../../infrastructure/database/schema';
import { LoginDto, RegisterDto } from './dto/auth.dto';

@Injectable()
export class AuthService {
  constructor(
    @Inject(DRIZZLE_DB) private readonly db: Database,
    private readonly jwtService: JwtService,
  ) {}

  async register(dto: RegisterDto) {
    const existing = await this.db
      .select()
      .from(users)
      .where(eq(users.email, dto.email));

    if (existing.length > 0) {
      throw new ConflictException('User with this email already exists');
    }

    const passwordHash = bcrypt.hashSync(dto.password, 10);
    const [newUser] = await this.db
      .insert(users)
      .values({
        email: dto.email,
        passwordHash,
        role: dto.role,
      })
      .returning();

    const token = this.generateToken(newUser.id, newUser.email, newUser.role);
    return {
      user: {
        id: newUser.id,
        email: newUser.email,
        role: newUser.role,
        createdAt: newUser.createdAt,
      },
      accessToken: token,
    };
  }

  async login(dto: LoginDto) {
    const [user] = await this.db
      .select()
      .from(users)
      .where(eq(users.email, dto.email));

    if (!user) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const isMatch = bcrypt.compareSync(dto.password, user.passwordHash);
    if (!isMatch) {
      throw new UnauthorizedException('Invalid credentials');
    }

    const token = this.generateToken(user.id, user.email, user.role);
    return {
      user: {
        id: user.id,
        email: user.email,
        role: user.role,
        createdAt: user.createdAt,
      },
      accessToken: token,
    };
  }

  generateToken(userId: string, email: string, role: string): string {
    return this.jwtService.sign(
      { sub: userId, email, role },
      {
        secret:
          process.env.JWT_SECRET || 'super_secret_jwt_key_marine_clean_2026',
        expiresIn: '7d',
      },
    );
  }
}

