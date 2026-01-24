import { drizzle } from 'drizzle-orm/postgres-js';
import postgres from 'postgres';
import * as schema from './schema';

const connectionString = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/agent_registry';

// Disable prefetch for serverless environments often used with Bun, though persistent is fine here.
const client = postgres(connectionString, { prepare: false });

export const db = drizzle(client, { schema });

// Helper to ensure FTS vector update on ingest
import { sql } from 'drizzle-orm';

export const toTsVector = (text: string) => sql`to_tsvector('english', ${text})`;
