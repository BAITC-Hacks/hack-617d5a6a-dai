import { useEffect, useMemo, useRef } from 'react'
import type { TransferOut } from '@/client/types.gen'
import { count } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useGraphView } from '@/stores/graph-view'

const DAYS = Array.from({ length: 31 }, (_, i) => i + 1)
const TICK_MS = 420
const dd = (d: number) => `${String(d).padStart(2, '0')}.07`

/** Таймлапс июля: проигрывание по дням и выбор диапазона дат на гистограмме переводов. */
export function GraphTimeline({ transfers }: { transfers: TransferOut[] }) {
  const play = useGraphView((s) => s.play)
  const playing = useGraphView((s) => s.playing)
  const range = useGraphView((s) => s.range)
  const setPlay = useGraphView((s) => s.setPlay)
  const setRange = useGraphView((s) => s.setRange)
  const resetTimeline = useGraphView((s) => s.resetTimeline)
  const drag = useRef<number | null>(null)

  useEffect(() => {
    if (!playing) return
    const id = setInterval(() => {
      const p = (useGraphView.getState().play ?? 0) + 1
      setPlay(Math.min(p, 31), p <= 31)
    }, TICK_MS)
    return () => clearInterval(id)
  }, [playing, setPlay])

  useEffect(() => {
    const up = () => (drag.current = null)
    window.addEventListener('mouseup', up)
    return () => window.removeEventListener('mouseup', up)
  }, [])

  const perDay = useMemo(() => {
    const a = new Array<number>(32).fill(0)
    for (const t of transfers) a[+t.date.slice(8, 10)]++
    return a
  }, [transfers])
  const max = Math.max(1, ...perDay)

  const togglePlay = () => setPlay(playing ? play : play == null || play >= 31 ? 1 : play, !playing)
  const label = play != null ? `${play} июля` : range ? (range[0] === range[1] ? dd(range[0]) : `${dd(range[0])}–${dd(range[1])}`) : 'весь июль'

  return (
    <div className="flex flex-none flex-col gap-1.5 border-t border-border bg-card px-3 pt-2 pb-2.5">
      <div className="flex items-center gap-2.5">
        <button
          type="button"
          onClick={togglePlay}
          title="Проиграть июль по дням"
          aria-label={playing ? 'Пауза' : 'Проиграть июль по дням'}
          className="size-[30px] cursor-pointer rounded-lg bg-foreground text-xs font-semibold text-background"
        >
          {playing ? '❚❚' : '▶'}
        </button>
        <span className="text-[13px] font-semibold whitespace-nowrap">Таймлапс</span>
        <span className="font-mono text-[13px] font-medium whitespace-nowrap text-foreground/90">{label}</span>
        {(play != null || range) && (
          <button
            type="button"
            onClick={resetTimeline}
            className="h-6 cursor-pointer rounded-md border border-border px-2 text-xs font-medium text-foreground/85 hover:bg-muted"
          >
            Сбросить
          </button>
        )}
        <span className="ml-auto truncate text-xs text-muted-foreground">
          по {count(transfers.length, 'переводу', 'переводам', 'переводам')} из загруженных карточек · выделите дни на гистограмме
        </span>
      </div>

      <div
        onMouseLeave={() => (drag.current = null)}
        title="Протяните по гистограмме, чтобы выбрать диапазон дат"
        className="grid h-10 cursor-crosshair grid-cols-[repeat(31,minmax(0,1fr))] items-end gap-0.5 select-none"
      >
        {DAYS.map((d) => {
          const inRange = range ? d >= range[0] && d <= range[1] : true
          const played = play == null || d <= play
          const h = perDay[d] ? Math.max(3, Math.round((perDay[d] / max) * 36)) : 0
          return (
            <div
              key={d}
              title={`${d} июля: ${count(perDay[d], 'перевод', 'перевода', 'переводов')} в загруженных карточках`}
              onMouseDown={() => {
                drag.current = d
                setRange([d, d])
              }}
              onMouseEnter={() => {
                if (drag.current != null) setRange([Math.min(drag.current, d), Math.max(drag.current, d)])
              }}
              className={cn(
                'flex h-full items-end rounded-xs',
                d === play ? 'bg-muted' : range && inRange ? 'bg-muted/50' : 'bg-transparent',
              )}
            >
              <div
                style={{ height: h }}
                className={cn('w-full rounded-t-xs', inRange && played ? 'bg-foreground/80' : 'bg-muted-foreground/30')}
              />
            </div>
          )
        })}
      </div>

      <input
        type="range"
        min={1}
        max={31}
        step={1}
        value={play ?? 31}
        onChange={(e) => setPlay(+e.target.value)}
        aria-label="День июля"
        className="m-0 w-full accent-foreground"
      />
      <div className="flex justify-between font-mono text-[11px] font-medium text-muted-foreground">
        <span>01.07</span>
        <span>08.07</span>
        <span>15.07</span>
        <span>22.07</span>
        <span>31.07.2026</span>
      </div>
    </div>
  )
}
