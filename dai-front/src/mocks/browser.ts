import { setupWorker } from 'msw/browser'
// Typed handlers are generated from openapi.json: import { handleXxx } from '@/client/msw.gen'
//
// Example:
//   import { handleListServices } from '@/client/msw.gen'
//   handleListServices({ body: [{ id: 1, title: 'Demo', price: 1000, description: null }] }),
//
// Remove a handler as soon as the real endpoint works (unhandled requests go to the backend).

export const worker = setupWorker()
