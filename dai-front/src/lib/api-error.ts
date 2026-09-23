type ValidationItem = { loc: (string | number)[]; msg: string; type: string }

function getDetail(error: unknown): unknown {
  if (error && typeof error === 'object' && 'detail' in error) {
    return (error as { detail: unknown }).detail
  }
  return undefined
}

/** Any FastAPI / network error -> one human-readable message. */
export function getErrorMessage(error: unknown): string {
  const detail = getDetail(error)
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return (detail as ValidationItem[]).map((d) => d.msg).join(', ')
  if (error instanceof Error) return error.message
  return 'Что-то пошло не так'
}

/** FastAPI 422 -> { fieldName: message } for react-hook-form setError. */
export function getFieldErrors(error: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  const detail = getDetail(error)
  if (Array.isArray(detail)) {
    for (const d of detail as ValidationItem[]) {
      const field = d.loc[d.loc.length - 1]
      if (field !== undefined && !(String(field) in out)) out[String(field)] = d.msg
    }
  }
  return out
}
