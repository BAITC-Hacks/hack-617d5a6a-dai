// narrowSymbol: без него ru-RU пишет «KZT» вместо «₸»
const money = { style: 'currency', currency: 'KZT', currencyDisplay: 'narrowSymbol' } as const
const kzt = new Intl.NumberFormat('ru-RU', { ...money, maximumFractionDigits: 0 })
const kztCompact = new Intl.NumberFormat('ru-RU', { ...money, notation: 'compact', maximumFractionDigits: 1 })
const day = new Intl.DateTimeFormat('ru-RU', { day: '2-digit', month: '2-digit', timeZone: 'UTC' })

/** 3848436 → «3 848 436 ₸» — карточка, списки. */
export const formatKzt = (value: number) => kzt.format(value)

/** 3848436 → «3,8 млн ₸» — подписи на графе. */
export const formatKztCompact = (value: number) => kztCompact.format(value)

/** «2026-07-12» → «12.07» (ДД.ММ, см. DESIGN.md). Дата без времени: разбираем в UTC, чтобы часовой пояс не сдвинул день. */
export const formatDay = (isoDate: string) => day.format(new Date(`${isoDate}T00:00:00Z`))
