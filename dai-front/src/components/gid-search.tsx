import { useEffect, useRef, useState } from 'react'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import { searchNodesOptions } from '@/client/@tanstack/react-query.gen'
import { GidText, SeedPill } from '@/components/top-list'
import { Skeleton } from '@/components/ui/skeleton'
import { count, formatScore } from '@/lib/format'
import { errorKind, metaQuery, useRoleInfo } from '@/lib/graph-data'
import { roleClass } from '@/lib/roles'
import { cn } from '@/lib/utils'

// Поиск по началу gid. Все gid начинаются с 10000000 — запрос имеет смысл с 9 цифр.
const MIN_LEN = 9

export function GidSearch() {
  const [q, setQ] = useState('')
  const [focused, setFocused] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()
  const roleInfo = useRoleInfo()
  const { data: meta } = useQuery(metaQuery())

  const digits = /^\d*$/.test(q)
  const { data, isLoading, error } = useQuery({
    ...searchNodesOptions({ query: { q, limit: 5 } }),
    enabled: digits && q.length >= MIN_LEN,
    placeholderData: keepPreviousData,
    meta: { silent: true },
  })

  // «/» — к поиску из любого места страницы, Esc — выйти из поля.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement
      const typing = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || (el instanceof HTMLElement && el.isContentEditable)
      if (e.key === '/' && !typing) {
        e.preventDefault()
        inputRef.current?.focus()
      }
      if (e.key === 'Escape' && el === inputRef.current) inputRef.current?.blur()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const go = (gid: string) => {
    setQ('')
    inputRef.current?.blur()
    void navigate({ to: '/nodes/$gid', params: { gid } })
  }

  const onEnter = () => {
    if (!digits || !q) return
    // Подсказки могут быть от прошлого ввода (keepPreviousData) — берём только совпадающую по началу.
    const first = data?.items.find((n) => n.gid.startsWith(q))
    go(q.length === 18 || !first ? q : first.gid)
  }

  const open = focused && !!q && digits
  const short = q.length < MIN_LEN
  const down = errorKind(error) === 'down'
  const items = data?.items ?? []
  const none = (data?.total === 0 && !isLoading) || errorKind(error) === 'notFound'
  const clients = meta ? count(meta.n_nodes, 'клиент', 'клиента', 'клиентов') : 'клиенты'

  return (
    <div className="flex flex-col gap-2 border-b p-4 pb-3.5">
      <label htmlFor="gid-search" className="text-[13px] font-medium text-muted-foreground">
        Перейти к клиенту по gid
      </label>
      <div className="relative">
        <div
          className={cn(
            'flex h-12 items-center gap-2 rounded-[10px] border bg-background px-3 focus-within:border-muted-foreground focus-within:ring-3 focus-within:ring-border',
            !digits && 'border-destructive focus-within:border-destructive',
          )}
        >
          <input
            id="gid-search"
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value.replace(/\s/g, ''))}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            onKeyDown={(e) => e.key === 'Enter' && onEnter()}
            placeholder="100000003684369100"
            inputMode="numeric"
            spellCheck={false}
            autoComplete="off"
            aria-invalid={!digits}
            className="min-w-0 flex-1 bg-transparent font-mono text-[17px] font-medium tracking-[.01em] outline-none placeholder:text-muted-foreground/60"
          />
          <kbd className="rounded-[5px] border px-1.5 py-px font-mono text-xs font-medium text-muted-foreground">/</kbd>
        </div>
        {!digits && <div className="mt-1.5 text-[13px] font-medium text-destructive">gid состоит только из цифр — 18 знаков</div>}

        {open && (
          <div className="absolute top-[54px] left-0 z-40 flex w-[420px] flex-col rounded-xl border bg-popover p-1.5 text-popover-foreground shadow-2xl">
            {short ? (
              <div className="px-2.5 pt-2.5 pb-3 text-sm/normal text-muted-foreground">
                Поиск идёт по началу gid. Все {clients} начинаются с <span className="font-mono font-semibold text-foreground">10000000</span>, поэтому подсказки появятся с 9–10 цифр.
              </div>
            ) : down ? (
              <div className="flex flex-col gap-1 px-2.5 py-3">
                <div className="text-[15px] font-semibold">Сервер анализа недоступен</div>
                <div className="text-[13.5px]/[1.45] text-muted-foreground">Поиск не выполнен. Это не значит, что клиента нет в выгрузке.</div>
              </div>
            ) : isLoading ? (
              <div className="flex flex-col gap-1.5 p-1.5">
                <Skeleton className="h-10 rounded-lg" />
                <Skeleton className="h-10 rounded-lg" />
                <Skeleton className="h-10 rounded-lg" />
              </div>
            ) : none ? (
              <div className="flex flex-col gap-1 px-2.5 py-3">
                <div className="text-[15px] font-semibold">Клиент с таким gid не найден в выгрузке</div>
                <div className="text-[13.5px]/[1.45] text-muted-foreground">
                  Нет gid, начинающихся с <span className="font-mono break-all text-foreground">{q}</span>.
                  {meta && ` В выгрузке ${clients} от ${meta.n_seed} seed.`}
                </div>
              </div>
            ) : (
              items.length > 0 && (
                <>
                  <div className="flex justify-between px-2.5 pt-1.5 pb-1 text-[12.5px] font-medium text-muted-foreground">
                    <span>Совпадения по началу gid</span>
                    <span className="font-mono">
                      найдено {data!.total}
                      {data!.total > items.length && ` · показано ${items.length}`}
                    </span>
                  </div>
                  {items.map((n) => {
                    const rc = roleClass(n.role)
                    const exact = n.gid === q
                    return (
                      <div
                        key={n.gid}
                        onMouseDown={(e) => {
                          e.preventDefault()
                          go(n.gid)
                        }}
                        className={cn('flex cursor-pointer flex-col gap-[5px] rounded-lg px-2.5 py-[9px] hover:bg-muted', exact && 'bg-muted/60')}
                      >
                        <div className="flex items-baseline gap-2">
                          <GidText gid={n.gid} className="text-[15px]" />
                          {exact && <span className="rounded border px-[5px] text-[11px] font-semibold text-muted-foreground">точное</span>}
                          <span className="ml-auto font-mono text-sm font-semibold">{formatScore(n.priority_score)}</span>
                        </div>
                        <div className="flex items-center gap-2 text-[13px] font-medium">
                          <span className={cn('flex items-center gap-1.5', rc.ink)}>
                            <span className={cn('size-2.5 rounded-full', rc.dot)} />
                            {roleInfo(n.role).title}
                          </span>
                          {n.is_seed && <SeedPill />}
                          {n.truncated_by_depth && (
                            <span className="rounded border-[1.5px] border-dashed border-muted-foreground px-[5px] text-[11.5px] text-muted-foreground">граница выгрузки</span>
                          )}
                          <span className="ml-auto text-xs font-normal text-muted-foreground">приоритет</span>
                        </div>
                      </div>
                    )
                  })}
                </>
              )
            )}
          </div>
        )}
      </div>
    </div>
  )
}
