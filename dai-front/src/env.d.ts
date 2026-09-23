/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend base URL. Dev: "/api" (Vite proxy). Prod: full https URL. */
  readonly VITE_API_URL: string
  /** "true" enables MSW mocks in dev */
  readonly VITE_MOCKS?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
