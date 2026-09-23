import { defineConfig } from '@hey-api/openapi-ts'

// Source of truth: ./openapi.json (FastAPI schema snapshot, committed to git).
// Refresh it:  curl -o openapi.json http://<backend-host>:8000/openapi.json && npm run gen
export default defineConfig({
  input: './openapi.json',
  output: 'src/client',
  plugins: [
    '@hey-api/client-fetch', // typed fetch client + SDK functions (sdk.gen.ts)
    '@tanstack/react-query', // xxxOptions / xxxQueryKey / xxxMutation
    'zod', // zXxx schemas from Pydantic models (forms)
    'msw', // typed mock handlers handleXxx (dev only)
  ],
})
