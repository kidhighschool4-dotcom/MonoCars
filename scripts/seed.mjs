import pg from 'pg'
import { readFileSync } from 'fs'
import { fileURLToPath } from 'url'
import { dirname, join } from 'path'

const { Client } = pg

const __dirname = dirname(fileURLToPath(import.meta.url))

const DATABASE_URL =
  'postgresql://postgres:*WTK_P3qQKw.H%2FH@db.tgnlpmgeswsowvhhhedb.supabase.co:5432/postgres'

const client = new Client({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
})

async function run() {
  console.log('Connecting to Supabase...')
  await client.connect()
  console.log('Connected.')

  const sql = readFileSync(join(__dirname, '../supabase/schema.sql'), 'utf-8')

  console.log('Running schema + seed (this may take ~30s)...')
  await client.query(sql)
  console.log('Done! All tables created and data seeded.')

  await client.end()
}

run().catch((err) => {
  console.error('Seed failed:', err.message)
  process.exit(1)
})
