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

/** P99 → «среди 1 % самых заметных», P29 → «больше, чем у 29 % клиентов». P = ⌊100·(1 − доля клиентов со значением ≥ x)⌋. */
export const formatPct = (p: number) => (p >= 90 ? `среди ${100 - p} % самых заметных` : `больше, чем у ${p} % клиентов`)

// Тексты пайплайна (evidence, role_checks, limitations, next_request, queue_rule) → слова аналитика, как в README.
// Порядок важен: «выше P95 по N фактам» раньше общего P\d+. \b в JS не видит кириллицу — ориентируемся на цифры.
const PLAIN: [RegExp, string | ((...m: string[]) => string)][] = [
  [/KZT/g, '₸'],
  [/ \((?:sink|pass-through)\)/g, ''],
  [/\(gather-scatter\)/g, '(сбор и раздача средств)'],
  [/\(fan-in\)/g, '(сбор от многих отправителей)'],
  [/\(fan-out\)/g, '(раздача многим получателям)'],
  [/betweenness [\d.,]+/g, 'посредничество между клиентами'],
  [/выше P95 по (\d+) факт(?:у|ам)/g, '$1 из 7 показателей среди 5 % самых заметных'],
  [/фактов выше P95 нет/g, 'нет показателей среди 5 % самых заметных'],
  [/\bP(\d{1,2})\b/g, (_, p) => formatPct(Number(p))],
  [/признаков скора/g, 'показателей приоритета'],
  [/скор (\d)/g, 'сумма баллов $1'],
  [/входов (\d)/g, 'отправителей $1'],
  [/выходов (\d)/g, 'получателей $1'],
  [/проход (\d)/g, 'сквозная сумма $1'],
  [/достижим от (\d+) seed/g, 'цепочки переводов от $1 seed'],
  [/входы неполны/g, 'входящие неполны'],
  [/поддержка (\d)/g, 'соответствие правилу $1'],
]

/** «координатор (gather-scatter): входов 24 (P99), … KZT; скор 41,2» → «координатор (сбор и раздача средств): отправителей 24 (среди 1 % самых заметных), … ₸; сумма баллов 41,2». */
export const humanize = (text: string) =>
  PLAIN.reduce((s, [re, to]) => (typeof to === 'string' ? s.replace(re, to) : s.replace(re, to)), text)

/**
 * gid из 18 цифр: общий префикс «10000000» и хвост «100» приглушаем, середину выделяем.
 * Все gid выгрузки начинаются с 10000000 — различается только середина.
 */
export const gidParts = (gid: string) =>
  /^\d{18}$/.test(gid) ? { pre: gid.slice(0, 8), mid: gid.slice(8, 15), suf: gid.slice(15) } : { pre: '', mid: gid, suf: '' }
