import type { NodeOut } from '@/client/types.gen'
import { useRoleInfo } from '@/lib/graph-data'
import { ROLE_ORDER } from '@/lib/roles'
import { Label } from './parts'

// Коды признаков пайплайна → подписи. Незнакомый код показываем как есть.
const METRIC: Record<string, string> = {
  in_deg: 'отправителей',
  out_deg: 'получателей',
  in_kzt: 'вход',
  out_kzt: 'выход',
  pass_kzt: 'проход',
  betweenness: 'посредничество',
  n_seed_upstream: 'seed выше по потоку',
  seeds: 'seed выше по потоку',
  depth: 'колено',
  'out/in': 'выход / вход',
}
const metric = (code: string) => METRIC[code] ?? code

/** «0.95» → «0,95», «3.8M» → «3,8 млн», «981K» → «981 тыс.». */
const ru = (s: string) =>
  s
    .replace(/(\d)\.(\d)/g, '$1,$2')
    .replace(/(\d)M\b/g, '$1 млн')
    .replace(/(\d)K\b/g, '$1 тыс.')

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

// «in_deg=24 (P99, +7.7)» — один вклад из score_terms
const TERM = /^(\S+)=(\S+) \((P\d+), ([+-]?[\d.]+)\)$/

/** Почему такой приоритет: два наибольших вклада (score_terms), признаки выше P95, сырой скор. */
export function PriorityWhy({ node }: { node: NodeOut }) {
  const raw = node.score_terms ?? ''
  const terms = raw ? raw.split('; ').map((t) => TERM.exec(t.trim())) : []
  const parsed = terms.length > 0 && terms.every((m) => m !== null)
  const facts = [
    node.n_terms_above_p95 != null && `выше P95: ${node.n_terms_above_p95} из 7 признаков`,
    node.priority_raw != null && `сырой скор ${ru(node.priority_raw.toFixed(1))}`,
  ].filter(Boolean)
  if (!raw && facts.length === 0) return null

  return (
    <div className="flex flex-col gap-2">
      <Label>Почему такой приоритет</Label>
      <div className="flex flex-col gap-2 rounded-xl border px-4 py-3">
        {parsed ? (
          <div className="grid grid-cols-[minmax(0,1fr)_auto_auto_auto] items-baseline gap-x-3 gap-y-1.5">
            <span className="text-xs text-muted-foreground">признак</span>
            <span className="text-right text-xs text-muted-foreground">значение</span>
            <span className="text-right text-xs text-muted-foreground">перцентиль</span>
            <span className="text-right text-xs text-muted-foreground">вклад</span>
            {terms.map((m) =>
              m ? (
                <div key={m[1]} className="contents">
                  <span className="text-[14px] font-medium">{metric(m[1])}</span>
                  <span className="text-right font-mono text-[14px] font-semibold whitespace-nowrap">
                    {ru(m[2])}
                    {m[1].endsWith('_kzt') && ' ₸'}
                  </span>
                  <span className="text-right font-mono text-[13px] text-muted-foreground">{m[3]}</span>
                  <span className="text-right font-mono text-[14px] font-semibold">{ru(m[4])}</span>
                </div>
              ) : null,
            )}
          </div>
        ) : (
          raw && <div className="font-mono text-[13px]/relaxed wrap-anywhere">{raw}</div>
        )}
        {facts.length > 0 && <div className="text-[12.5px] text-muted-foreground">{facts.join(' · ')}</div>}
      </div>
    </div>
  )
}

/** Проверка правила роли из role_checks: «coordinator:in_deg 24≥3 ✓, out_deg 62≥5 ✓». Не разобралось — текст как есть. */
export function RoleChecks({ checks }: { checks: string }) {
  const roleInfo = useRoleInfo()
  const i = checks.indexOf(':')
  const body = checks.slice(i + 1).trim()
  const items = body.split(', ')
  const isList = i > 0 && items.every((x) => /[✓✗]$/.test(x))

  if (!isList) {
    // peripheral: «правила других ролей не сработали; ближе всего coordinator, поддержка 0.881»
    const text = body.replace(/\b[a-z]+\b/g, (w) => {
      const r = ROLE_ORDER.find((x) => x === w)
      return r ? `«${roleInfo(r).title}»` : w
    })
    return <div className="rounded-xl border px-4 py-3 text-[14px]/relaxed">{capitalize(ru(text))}</div>
  }

  return (
    <ul className="flex flex-col gap-1.5 rounded-xl border px-4 py-3">
      {items.map((x) => {
        const ok = x.endsWith('✓')
        const text = x.slice(0, -1).trim()
        const m = /^([a-z_/]+)\s*(.*)$/.exec(text)
        return (
          <li key={x} className="flex items-baseline gap-2.5 text-[14px]">
            <span className={ok ? 'font-mono font-bold' : 'font-mono font-bold text-muted-foreground'}>{ok ? '✓' : '✗'}</span>
            <span>{m ? metric(m[1]) : text}</span>
            {m?.[2] && <span className="font-mono font-semibold">{ru(m[2].replace(/\s*([≥≤<>=∈])\s*/g, ' $1 ').trim())}</span>}
          </li>
        )
      })}
    </ul>
  )
}

/** Связь с делом: из скольких seed деньги доходят до узла. Путей в API пока нет. */
export function CaseLink({ node }: { node: NodeOut }) {
  const n = node.n_seed_upstream
  if (n == null) return null
  return (
    <div className="flex flex-col gap-2">
      <Label>Связь с делом</Label>
      <div className="flex items-baseline gap-3 rounded-xl border px-4 py-3">
        <span className="font-mono text-[22px]/none font-bold">{n}</span>
        <span className="text-[13.5px]/snug">
          {n > 0
            ? 'seed, из которых деньги доходят до узла по цепочкам переводов'
            : 'из seed деньги до узла по переводам выгрузки не доходят'}
        </span>
      </div>
    </div>
  )
}

/** Что запросить дальше (next_request) и ограничения данных по узлу (limitations через «; »). */
export function NextStep({ node }: { node: NodeOut }) {
  const limits = node.limitations ? node.limitations.split('; ') : []
  if (!node.next_request && limits.length === 0) return null
  return (
    <div className="flex flex-col divide-y rounded-xl border">
      {node.next_request && (
        <div className="flex flex-col gap-1.5 px-4 py-3">
          <Label>Рекомендуется запросить</Label>
          <div className="text-[15px]/snug font-medium">{node.next_request}</div>
        </div>
      )}
      {limits.length > 0 && (
        <div className="flex flex-col gap-1.5 px-4 py-3">
          <Label>Ограничения данных по узлу</Label>
          <ul className="flex flex-col gap-1 text-[13.5px]/snug">
            {limits.map((l) => (
              <li key={l} className="flex gap-2">
                <span className="text-muted-foreground">·</span>
                {l}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
