// narrowSymbol: без него ru-RU пишет «KZT» вместо «₸»
const money = { style: 'currency', currency: 'KZT', currencyDisplay: 'narrowSymbol' } as const
const kzt = new Intl.NumberFormat('ru-RU', { ...money, maximumFractionDigits: 0 })
const kztCompact = new Intl.NumberFormat('ru-RU', { ...money, notation: 'compact', maximumFractionDigits: 1 })
const int = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 })
const day = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'UTC' })
const dayLong = new Intl.DateTimeFormat('ru-RU', { day: 'numeric', month: 'long', timeZone: 'UTC' })

/** 3848436 → «3 848 436 ₸» — карточка, списки. */
export const formatKzt = (value: number) => kzt.format(value)

/** 3848436 → «3,8 млн ₸» — подписи на графе, шапка. */
export const formatKztCompact = (value: number) => kztCompact.format(value)

/** 2248 → «2 248». */
export const formatInt = (value: number) => int.format(value)

/** 0.9931 → «0,99»; null → «—». */
export const formatScore = (value: number | null | undefined) => (value == null ? '—' : value.toFixed(2).replace('.', ','))

const utc = (isoDate: string) => new Date(`${isoDate}T00:00:00Z`)

/** «2026-07-12» → «12.07» (ДД.ММ, см. DESIGN.md). Дата без времени: разбираем в UTC, чтобы часовой пояс не сдвинул день. */
export const formatDay = (isoDate: string) => day.format(utc(isoDate))

/** «2026-07-12» → «12 июля». */
export const formatDayLong = (isoDate: string) => dayLong.format(utc(isoDate))

/** Русское множественное число: plural(3, 'узел', 'узла', 'узлов') → «узла». */
export function plural(n: number, one: string, few: string, many: string) {
  const m10 = n % 10
  const m100 = n % 100
  if (m10 === 1 && m100 !== 11) return one
  if (m10 >= 2 && m10 <= 4 && (m100 < 12 || m100 > 14)) return few
  return many
}

/** «3 узла», «21 узел». */
export const count = (n: number, one: string, few: string, many: string) => `${formatInt(n)} ${plural(n, one, few, many)}`

/**
 * gid из 18 цифр: общий префикс «10000000» и хвост «100» приглушаем, середину выделяем.
 * Все gid выгрузки начинаются с 10000000 — различается только середина.
 */
export const gidParts = (gid: string) =>
  /^\d{18}$/.test(gid) ? { pre: gid.slice(0, 8), mid: gid.slice(8, 15), suf: gid.slice(15) } : { pre: '', mid: gid, suf: '' }
