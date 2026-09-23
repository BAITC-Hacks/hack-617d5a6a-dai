import { useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import type { TransferPair } from '@/client/types.gen'
import { Button } from '@/components/ui/button'
import { formatDay, formatKzt } from '@/lib/format'
import { Gid, Label } from './parts'

const CAP = 50 // у топ-1 227 пар: первые 50, остальные по кнопке
const STATUSES: TransferPair['chronology_status'][] = ['вход раньше выхода', 'тот же день, порядок неизвестен', 'выход раньше входа']

const lag = (d: number) => `${d > 0 ? '+' : d < 0 ? '−' : ''}${Math.abs(d)} дн.`

/** Хронология: пары «вход → выход» по дате входа. Статус — наблюдение по датам, не вывод. */
export function Pairs({ pairs }: { pairs: TransferPair[] }) {
  const navigate = useNavigate()
  const [all, setAll] = useState(false)
  const go = (gid: string) => navigate({ to: '/nodes/$gid', params: { gid } })
  const matched = pairs.filter((p) => p.matched_1to1).length
  const chip = 'inline-flex h-6 items-center gap-1.5 rounded-md bg-muted px-2 text-[12.5px] font-medium'

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-col gap-2 rounded-xl border px-3.5 py-3">
        <Label>Пары «вход → выход» по дате входа</Label>
        <div className="flex flex-wrap gap-1.5">
          {STATUSES.map((s) => {
            const n = pairs.filter((p) => p.chronology_status === s).length
            return n > 0 ? (
              <span key={s} className={chip}>
                {s}
                <span className="font-mono font-semibold">{n}</span>
              </span>
            ) : null
          })}
          {matched > 0 && (
            <span className={chip}>
              быстрый транзит 1-к-1
              <span className="font-mono font-semibold">{matched}</span>
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-col">
        {(all ? pairs : pairs.slice(0, CAP)).map((p, k) => (
          <div key={k} className="flex flex-col gap-0.5 border-b border-border/60 px-0.5 py-2.5">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1 pb-0.5 text-[13px]">
              <span className="font-mono font-semibold">
                {formatDay(p.in_date)} → {formatDay(p.out_date)}
              </span>
              <span className="font-mono text-muted-foreground">{lag(p.lag_days)}</span>
              {p.matched_1to1 && (
                <span title="Пара вошла в быстрый транзит: сопоставление 1-к-1, лаг 0–2 дня" className="rounded-md border px-1.5 text-[11.5px] font-semibold">
                  1-к-1
                </span>
              )}
              <span className="ml-auto rounded-md bg-muted px-2 py-px text-xs font-medium">{p.chronology_status}</span>
            </div>
            <CpRow label="от" gid={p.in_src} sum={p.in_sum} onClick={go} />
            <CpRow label="кому" gid={p.out_dst} sum={p.out_sum} onClick={go} />
          </div>
        ))}
      </div>
      {!all && pairs.length > CAP && (
        <Button variant="outline" onClick={() => setAll(true)}>
          Показать все {pairs.length}
        </Button>
      )}
      <div className="text-[12.5px]/normal text-muted-foreground">
        Пара сопоставляет вход и выход по датам и не доказывает, что это те же деньги. Даты с точностью до дня, порядок внутри дня неизвестен.
      </div>
    </div>
  )
}

function CpRow({ label, gid, sum, onClick }: { label: string; gid: string; sum: number; onClick: (gid: string) => void }) {
  return (
    <button
      type="button"
      onClick={() => onClick(gid)}
      className="grid grid-cols-[36px_minmax(0,1fr)_auto] items-center gap-2 rounded-md px-0.5 py-0.5 text-left text-[13.5px] hover:bg-muted/60"
    >
      <span className="text-muted-foreground">{label}</span>
      <Gid gid={gid} className="truncate font-medium" />
      <span className="font-mono font-semibold whitespace-nowrap">{formatKzt(sum)}</span>
    </button>
  )
}
