import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import type { EdgeOut, NodeCard as NodeCardData, TransferOut } from '@/client/types.gen'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { getErrorMessage } from '@/lib/api-error'
import { count, formatDayLong, formatKzt, formatScore } from '@/lib/format'
import { errorKind, nodeQuery, useNodeIndex, useQueue, useRoleInfo } from '@/lib/graph-data'
import { roleClass } from '@/lib/roles'
import { cn } from '@/lib/utils'
import { CaseLink, NextStep, PriorityWhy, RoleChecks } from './node-card/insights'
import { Pairs } from './node-card/pairs'
import { Gid, Label, SeedPill } from './node-card/parts'

const tx = (n: number) => count(n, 'перевод', 'перевода', 'переводов')

export function NodeCard({ gid }: { gid: string }) {
  const { data, error, isPending } = useQuery(nodeQuery(gid))

  if (isPending) return <CardSkeleton />
  if (error) {
    const text = errorKind(error) === 'down' ? 'Сервер анализа недоступен. Повторите запрос.' : getErrorMessage(error)
    return (
      <div className="flex flex-col gap-1.5 px-5 py-7">
        <div className="text-[15px] font-semibold">Карточка не загружена</div>
        <div className="text-sm/relaxed text-muted-foreground">{text}</div>
      </div>
    )
  }
  // key: вкладка и «Скопировано» сбрасываются при переходе на другой gid
  return <CardBody key={gid} gid={gid} card={data} />
}

function CardSkeleton() {
  return (
    <div className="flex flex-col gap-3.5 p-5">
      <Skeleton className="h-7.5 w-75" />
      <Skeleton className="h-5.5 w-45" />
      <Skeleton className="h-18 rounded-xl" />
      <Skeleton className="h-32 rounded-xl" />
      <div className="grid grid-cols-2 gap-2.5">
        <Skeleton className="h-22 rounded-xl" />
        <Skeleton className="h-22 rounded-xl" />
      </div>
      <Skeleton className="h-55 rounded-xl" />
    </div>
  )
}

function CardBody({ gid, card }: { gid: string; card: NodeCardData }) {
  const nd = card.node
  const roleInfo = useRoleInfo()
  const { queue } = useQueue()
  const rank = nd.in_queue ? queue.findIndex((n) => n.gid === gid) + 1 : 0
  const pairs = card.pairs ?? []
  const [tab, setTab] = useState<'cp' | 'tx' | 'pairs'>('cp')
  const [copied, setCopied] = useState(false)

  const role = roleInfo(nd.role)
  const rc = roleClass(nd.role)
  const trunc = nd.truncated_by_depth
  const depthLabel =
    nd.depth === 0 ? 'колено 0 · исходный известный клиент' : nd.depth === 4 ? 'колено 4 · граница выгрузки' : `колено ${nd.depth} из 4`
  const hasLinks = card.in_edges.length + card.out_edges.length + card.transfers.length > 0

  const copy = () => {
    navigator.clipboard?.writeText(gid).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1400)
  }

  return (
    <div className="flex flex-col gap-4.5 px-5 pt-5 pb-7">
      <div className="flex flex-col gap-2.5">
        <Label>Клиент</Label>
        <div className="flex items-center gap-2">
          <Gid gid={gid} className="text-[25px] font-medium tracking-tight" />
          <Button variant="outline" className="ml-auto" title="Скопировать gid" onClick={copy}>
            {copied ? 'Скопировано' : 'Копировать'}
          </Button>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn('inline-flex h-7.5 items-center gap-2 rounded-lg pr-3 pl-2.5 text-[15px] font-semibold', rc.badge)}>
            <span className={cn('size-3 rounded-full', rc.dot)} />
            {role.title}
          </span>
          {nd.is_seed && <SeedPill />}
          {trunc && (
            <span className="inline-flex h-6.5 items-center rounded-md border-[1.5px] border-dashed border-foreground/70 px-2.5 text-[12.5px] font-semibold">
              граница выгрузки
            </span>
          )}
          {nd.in_queue && (
            <span className="inline-flex h-6.5 items-center rounded-md bg-muted px-2.5 text-[12.5px] font-medium whitespace-nowrap">
              {rank > 0 ? `№ ${rank} в очереди` : 'в очереди проверки'}
            </span>
          )}
          {nd.fast_transit_flag && (
            <span
              title="Пары вход → выход 1-к-1 с лагом 0–2 дня и близкими суммами (0,8–1,2)"
              className="inline-flex h-6.5 items-center rounded-md border-[1.5px] px-2.5 text-[12.5px] font-medium whitespace-nowrap"
            >
              признаки быстрого транзита
              {nd.fast_transit_pairs != null && ` · ${count(nd.fast_transit_pairs, 'пара', 'пары', 'пар')}`}
            </span>
          )}
        </div>
        {role.description && <div className="text-[13.5px] text-muted-foreground">{role.description}</div>}
      </div>

      <div className="grid grid-cols-[1.1fr_1fr] overflow-hidden rounded-xl border">
        <div className="flex flex-col gap-1.5 border-r px-4 py-3.5">
          <Label>Приоритет проверки</Label>
          <div className="font-mono text-[34px]/none font-bold">{formatScore(nd.priority_score)}</div>
          <span className="h-1.25 overflow-hidden rounded-full bg-muted">
            <span className="block h-full bg-primary" style={{ width: `${Math.round(nd.priority_score * 100)}%` }} />
          </span>
          <span className="text-xs/snug text-muted-foreground">Шкала внутри выгрузки, не вероятность нарушения</span>
        </div>
        <div className="flex flex-col gap-1.5 px-4 py-3.5">
          <Label>Соответствие правилу роли</Label>
          <div className="flex items-baseline gap-1.5">
            <span className="font-mono text-2xl/tight font-semibold">{formatScore(nd.role_score)}</span>
            <span className="text-[13px] text-muted-foreground">из 1</span>
          </div>
          <div className="text-xs/snug text-muted-foreground">насколько данные поддерживают правило, не вероятность</div>
        </div>
      </div>

      <PriorityWhy node={nd} />

      <div className="flex flex-col gap-2">
        <Label>Основание роли</Label>
        <div className="min-h-29.5 rounded-xl bg-muted px-4 py-3.5 text-[16.5px]/normal font-medium text-pretty wrap-anywhere">
          {nd.evidence}
        </div>
        {nd.role_checks && <RoleChecks checks={nd.role_checks} />}
        <div className="flex flex-wrap gap-4 text-[13.5px] text-muted-foreground">
          <span>{depthLabel}</span>
          <span className="whitespace-nowrap">кластер {nd.cluster_id}</span>
        </div>
      </div>

      <CaseLink node={nd} />

      <div className="grid grid-cols-2 gap-2.5">
        <div className="flex flex-col gap-1 rounded-xl border px-3.5 py-3">
          <Label>← Входящие</Label>
          <div className="font-mono text-[19px] font-bold whitespace-nowrap">{formatKzt(nd.in_kzt)}</div>
          <div className="text-[13.5px]">{count(nd.in_deg, 'отправитель', 'отправителя', 'отправителей')}</div>
          <div className="text-[13.5px] text-muted-foreground">{tx(nd.in_tx)}</div>
        </div>
        <div className={cn('flex flex-col gap-1 rounded-xl border px-3.5 py-3', trunc && 'border-dashed border-muted-foreground/50')}>
          <Label>Исходящие →</Label>
          {trunc ? (
            <>
              <div className="text-[15px]/snug font-semibold">Исходящие переводы не выгружены</div>
              <div className="text-[13px] text-muted-foreground">4-е колено — последнее в выгрузке</div>
            </>
          ) : (
            <>
              <div className="font-mono text-[19px] font-bold whitespace-nowrap">{formatKzt(nd.out_kzt)}</div>
              <div className="text-[13.5px]">{count(nd.out_deg, 'получатель', 'получателя', 'получателей')}</div>
              <div className="text-[13.5px] text-muted-foreground">{tx(nd.out_tx)}</div>
            </>
          )}
        </div>
      </div>

      <NextStep node={nd} />

      {!hasLinks ? (
        <div className="flex flex-col gap-1 rounded-xl bg-muted px-4 py-5.5">
          <div className="font-semibold">Связей в выгрузке нет</div>
          <div className="text-sm/relaxed text-muted-foreground">
            За 1–31 июля 2026 у клиента нет ни входящих, ни исходящих переводов в выгрузке.
            {nd.is_seed && ' Как seed он остаётся в результате.'}
          </div>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex rounded-[10px] bg-muted p-0.75">
            <TabButton active={tab === 'cp'} onClick={() => setTab('cp')}>
              Контрагенты · {card.in_edges.length + card.out_edges.length}
            </TabButton>
            <TabButton active={tab === 'tx'} onClick={() => setTab('tx')}>
              Переводы · {card.transfers.length}
            </TabButton>
            {pairs.length > 0 && (
              <TabButton active={tab === 'pairs'} onClick={() => setTab('pairs')}>
                Пары · {pairs.length}
              </TabButton>
            )}
          </div>
          {tab === 'cp' ? <Counterparties card={card} /> : tab === 'tx' ? <Transfers gid={gid} card={card} /> : <Pairs pairs={pairs} />}
        </div>
      )}
    </div>
  )
}

function TabButton({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn('h-8.5 flex-1 rounded-lg text-sm font-semibold', active ? 'bg-background shadow-sm' : 'hover:bg-background/50')}
    >
      {children}
    </button>
  )
}

function Counterparties({ card }: { card: NodeCardData }) {
  const ins = new Set(card.in_edges.map((e) => e.src))
  const outs = new Set(card.out_edges.map((e) => e.dst))
  const bySum = (a: EdgeOut, b: EdgeOut) => b.sum_kzt - a.sum_kzt
  return (
    <div className="flex flex-col gap-4">
      {card.in_edges.length > 0 && (
        <CpList
          title="← Отправители"
          rows={[...card.in_edges].sort(bySum).map((e) => ({ gid: e.src, e }))}
          both={(g) => outs.has(g)}
        />
      )}
      {card.out_edges.length > 0 && (
        <CpList
          title="Получатели →"
          rows={[...card.out_edges].sort(bySum).map((e) => ({ gid: e.dst, e }))}
          both={(g) => ins.has(g)}
        />
      )}
      {card.node.truncated_by_depth && (
        <div className="rounded-[10px] border-[1.5px] border-dashed border-muted-foreground/60 px-3.5 py-3 text-sm/relaxed">
          Исходящие переводы не выгружены (4-е колено). Это граница выгрузки, а не вывод о том, что деньги остались у клиента.
        </div>
      )}
    </div>
  )
}

function CpList({ title, rows, both }: { title: string; rows: { gid: string; e: EdgeOut }[]; both: (gid: string) => boolean }) {
  const index = useNodeIndex()
  const roleInfo = useRoleInfo()
  const navigate = useNavigate()
  return (
    <div className="flex flex-col">
      <div className="flex items-baseline border-b px-0.5 pb-1.5">
        <span className="text-sm font-semibold">{title}</span>
        <span className="ml-auto text-[12.5px] text-muted-foreground">сумма за месяц · переводов</span>
      </div>
      {rows.map(({ gid, e }) => {
        const n = index.get(gid)
        const rc = roleClass(n?.role)
        return (
          <button
            key={gid}
            type="button"
            onClick={() => navigate({ to: '/nodes/$gid', params: { gid } })}
            className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-2.5 gap-y-0.5 border-b border-border/60 px-0.5 py-2.25 text-left hover:bg-muted/60"
          >
            <Gid gid={gid} className="text-sm font-medium" />
            <span className="text-right font-mono text-sm font-semibold whitespace-nowrap">{formatKzt(e.sum_kzt)}</span>
            <span className={cn('flex flex-wrap items-center gap-1.5 text-[12.5px] font-medium', rc.ink)}>
              <span className={cn('size-2 rounded-full', rc.dot)} />
              {roleInfo(n?.role).title}
              {n?.is_seed && <SeedPill small />}
              {both(gid) && <span className="text-xs text-foreground/70">⇄ встречные переводы</span>}
            </span>
            <span className="text-right text-[12.5px] text-muted-foreground">{tx(e.n_tx)}</span>
          </button>
        )
      })}
    </div>
  )
}

const TICKS = [1, 8, 15, 22, 31]
const HALF = 48 // px: высота столбика дня с максимальной суммой

function Transfers({ gid, card }: { gid: string; card: NodeCardData }) {
  const navigate = useNavigate()
  const isIn = (t: TransferOut) => t.dst === gid

  // ponytail: выгрузка — ровно июль 2026, день берём из даты; другой период → считать дни от min(date)
  const agg = Array.from({ length: 32 }, () => ({ i: 0, o: 0, ni: 0, no: 0 }))
  const days: { date: string; rows: TransferOut[]; i: number; o: number }[] = []
  for (const t of card.transfers) {
    const a = agg[Number(t.date.slice(8))] ?? agg[0]
    let d = days.at(-1)
    if (d?.date !== t.date) days.push((d = { date: t.date, rows: [], i: 0, o: 0 }))
    d.rows.push(t)
    if (isIn(t)) {
      a.i += t.sum_kzt
      a.ni++
      d.i++
    } else {
      a.o += t.sum_kzt
      a.no++
      d.o++
    }
  }
  const max = Math.max(1, ...agg.map((a) => Math.max(a.i, a.o)))
  const h = (v: number) => (v ? Math.max(4, Math.round((Math.log(v + 1) / Math.log(max + 1)) * HALF)) : 0)
  const fi = card.transfers.find(isIn)
  const fo = card.transfers.find((t) => t.src === gid)
  const month = agg.slice(1)

  return (
    <div className="flex flex-col gap-3.5">
      <div className="flex flex-col gap-1.5 rounded-xl border px-3 pt-3 pb-2.5">
        <Label>Июль 2026 · входы сверху, выходы снизу</Label>
        <div className="grid h-26 grid-cols-[repeat(31,minmax(0,1fr))] gap-0.5">
          {month.map((a, k) => (
            <div
              key={k}
              title={`${k + 1} июля: вход ${a.ni ? `${formatKzt(a.i)} (${a.ni})` : '—'}, выход ${a.no ? `${formatKzt(a.o)} (${a.no})` : '—'}`}
              className={cn('grid grid-rows-2 rounded-[3px]', a.ni && a.no ? 'bg-border' : 'bg-muted/60')}
            >
              <div className="flex items-end border-b border-muted-foreground/40">
                <div className="w-full rounded-t-[2px] bg-foreground/80" style={{ height: h(a.i) }} />
              </div>
              <div className="flex items-start">
                <div
                  className={cn('w-full rounded-b-[2px] bg-background', a.o > 0 && 'border-[1.5px] border-t-0 border-foreground/80')}
                  style={{ height: h(a.o) }}
                />
              </div>
            </div>
          ))}
        </div>
        <div className="grid grid-cols-[repeat(31,minmax(0,1fr))] gap-0.5">
          {month.map((_, k) => (
            <div key={k} className="text-center font-mono text-[10.5px] font-medium text-muted-foreground">
              {TICKS.includes(k + 1) ? k + 1 : ''}
            </div>
          ))}
        </div>
        <div className="flex flex-wrap gap-x-3.5 gap-y-1.5 pt-1 text-[13px]">
          <span>Первый вход: {fi ? formatDayLong(fi.date) : 'нет'}</span>
          <span>первый выход: {fo ? formatDayLong(fo.date) : card.node.truncated_by_depth ? 'не выгружены' : 'нет'}</span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <span className="size-3 rounded-[3px] bg-border" />
            вход и выход в один день
          </span>
        </div>
      </div>

      {days.map((d) => (
        <div key={d.date} className="flex flex-col">
          <div className="flex flex-wrap items-center gap-2 border-b px-0.5 py-1.5">
            <span className="text-[15px] font-semibold">{formatDayLong(d.date)}</span>
            <span className="text-[12.5px] text-muted-foreground">
              {[d.i && count(d.i, 'вход', 'входа', 'входов'), d.o && count(d.o, 'выход', 'выхода', 'выходов')].filter(Boolean).join(' · ')}
            </span>
            {d.i > 0 && d.o > 0 && (
              <span className="ml-auto inline-flex h-5.5 items-center rounded-md bg-border px-2 text-[12.5px] font-medium">
                тот же день, порядок неизвестен
              </span>
            )}
          </div>
          {d.rows.map((t, k) => {
            const inbound = isIn(t)
            const cp = inbound ? t.src : t.dst
            return (
              <button
                key={k}
                type="button"
                onClick={() => navigate({ to: '/nodes/$gid', params: { gid: cp } })}
                className="grid grid-cols-[74px_minmax(0,1fr)_auto] items-center gap-2.5 border-b border-border/60 px-0.5 py-2 text-left hover:bg-muted/60"
              >
                <span className="flex items-center gap-1.5 text-[13px] font-semibold">
                  <span className={cn('size-2.5 rounded-[2px] border-[1.5px] border-foreground/80', inbound ? 'bg-foreground/80' : 'bg-background')} />
                  {inbound ? 'вход' : 'выход'}
                </span>
                <span className="truncate font-mono text-[13.5px] font-medium">
                  <span className="text-muted-foreground">{inbound ? 'от' : 'кому'} </span>
                  <Gid gid={cp} />
                </span>
                <span className="font-mono text-sm font-semibold whitespace-nowrap">{formatKzt(t.sum_kzt)}</span>
              </button>
            )
          })}
        </div>
      ))}
      <div className="text-[12.5px]/normal text-muted-foreground">
        Даты с точностью до дня. Внутри одного дня порядок переводов по данным не определяется.
      </div>
    </div>
  )
}
