import { useEffect, useRef, type ReactElement } from 'react'
import { RoleIcon } from '@/components/role-icon'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useRoleInfo } from '@/lib/graph-data'
import { ROLE_ORDER, type Role } from '@/lib/roles'
import { cn } from '@/lib/utils'

export type LegendItem = Role | 'seed' | 'boundary'

// Подсказки «как читать» — гипотезы для аналитика, без порогов (пороги — в карточке узла).
const LEGEND: Record<LegendItem, { hint: string; graph: string; title?: string }> = {
  coordinator: {
    hint: 'Связывает части сети: деньги доходят до него от нескольких seed и расходятся дальше. Правило и пороги — в карточке узла.',
    graph: 'оранжевый ромб',
  },
  distributor: {
    hint: 'Раздаёт деньги многим получателям. Следующее звено схемы — среди его получателей.',
    graph: 'розовая звезда',
  },
  consolidator: {
    hint: 'Собирает деньги от многих отправителей — возможная точка консолидации. Смотрите отправителей и seed выше по потоку.',
    graph: 'синий треугольник вниз (воронка)',
  },
  transit: {
    hint: 'Быстро передаёт полученное дальше. Смотрите вкладку «Пары»: вход → выход и лаг в днях.',
    graph: 'жёлтый треугольник вправо',
  },
  terminal: {
    hint: 'Деньги приходят, исходящих в выгрузке нет. Не путать с границей выгрузки на 4-м колене.',
    graph: 'серо-голубой квадрат',
  },
  peripheral: {
    hint: 'Признаков роли не набралось. Обычно низкий приоритет проверки.',
    graph: 'светло-серый круг',
  },
  seed: {
    title: 'seed — известный клиент',
    hint: 'Один из 81 клиента из исходного запроса — от них построена выгрузка на четыре колена. Входящие у seed неполные: деньги извне выборки не видны.',
    graph: 'белая обводка',
  },
  boundary: {
    title: 'граница выгрузки',
    hint: '4-е колено обхода: исходящие переводы не выгружались. Отсутствие исходящих — ограничение данных, а не вывод, что деньги остались у клиента.',
    graph: 'пунктирная обводка',
  },
}

const isRole = (item: LegendItem): item is Role => item !== 'seed' && item !== 'boundary'

/** Значок пункта легенды: форма роли, двойное кольцо seed или пунктир границы. */
export function LegendIcon({ item }: { item: LegendItem }) {
  if (item === 'seed') return <span className="size-3.5 flex-none rounded-full border-[3.5px] border-double border-current" />
  if (item === 'boundary') return <span className="size-3.5 flex-none rounded-full border-2 border-dashed border-current opacity-80" />
  return <RoleIcon role={item} className="size-4" />
}

/** Подсказка легенды поверх любого фокусируемого элемента (children — кнопка). */
export function LegendTooltip({ item, children }: { item: LegendItem; children: ReactElement }) {
  const roleInfo = useRoleInfo()
  const { hint, graph } = LEGEND[item]
  const { title, description } = isRole(item) ? roleInfo(item) : { title: LEGEND[item].title, description: '' }
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent side="bottom" sideOffset={6} className="max-w-[300px] flex-col items-stretch gap-1.5 px-3 py-2.5 text-left text-[12.5px] leading-snug">
        <div className="flex items-center gap-2 text-[13.5px] font-semibold">
          <LegendIcon item={item} />
          {title}
        </div>
        {description && <p className="text-background/90">{description}</p>}
        <p className="text-background/75">
          {isRole(item) && <span className="font-semibold text-background/90">Как читать: </span>}
          {hint}
        </p>
        <p className="mt-0.5 border-t border-background/15 pt-1.5 text-[11.5px] text-background/60">На графе — {graph}</p>
      </TooltipContent>
    </Tooltip>
  )
}

/** Пункт легенды в шапке: значок + подпись, подсказка по наведению и фокусу, клик открывает справочник. */
export function LegendEntry({ item, onOpen }: { item: LegendItem; onOpen: (item: LegendItem) => void }) {
  const roleInfo = useRoleInfo()
  const label = isRole(item) ? roleInfo(item).title : LEGEND[item].title
  return (
    <LegendTooltip item={item}>
      <button
        type="button"
        onClick={() => onOpen(item)}
        className="flex cursor-pointer items-center gap-[7px] rounded-sm text-[13.5px] font-medium whitespace-nowrap outline-none hover:text-foreground/75 focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <LegendIcon item={item} />
        {label}
      </button>
    </LegendTooltip>
  )
}

/** Справочник узлов: все роли и отметки с пояснениями, выезжает справа. `item` — пункт, по которому кликнули: подсвечен и прокручен в видимую область. */
export function LegendSheet({ item, onClose }: { item: LegendItem | null; onClose: () => void }) {
  const roleInfo = useRoleInfo()
  const active = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (item) requestAnimationFrame(() => active.current?.scrollIntoView({ block: 'nearest' }))
  }, [item])

  const entry = (it: LegendItem) => {
    const { hint, graph } = LEGEND[it]
    const { title, description } = isRole(it) ? roleInfo(it) : { title: LEGEND[it].title, description: '' }
    const on = it === item
    return (
      <div key={it} ref={on ? active : undefined} className={cn('flex gap-3 rounded-xl px-3 py-3', on && 'bg-muted')}>
        <span className="flex h-6 items-center">
          <LegendIcon item={it} />
        </span>
        <div className="flex min-w-0 flex-col gap-1">
          <div className="text-[15px] font-semibold">{title}</div>
          {description && <p className="text-[13.5px] leading-snug">{description}</p>}
          <p className="text-[13px] leading-snug text-muted-foreground">
            {isRole(it) && <span className="font-medium text-foreground/80">Как читать: </span>}
            {hint}
          </p>
          <p className="text-xs text-muted-foreground">На графе — {graph}</p>
        </div>
      </div>
    )
  }

  return (
    // Немодальная панель без затемнения: граф за ней можно зумить и двигать, клик мимо её не закрывает — только × или Esc
    <Sheet open={item !== null} onOpenChange={(open) => !open && onClose()} modal={false} disablePointerDismissal>
      <SheetContent side="right" overlay={false} className="w-[440px] gap-0 data-[side=right]:sm:max-w-[440px]">
        <SheetHeader className="border-b">
          <SheetTitle className="text-lg">Справочник узлов</SheetTitle>
          <SheetDescription>Роли — гипотезы по правилам с порогами, а не выводы о клиенте. Пороги конкретного узла — в его карточке.</SheetDescription>
        </SheetHeader>
        <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-auto p-3">
          <div className="px-3 pt-1 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Роли</div>
          {ROLE_ORDER.map(entry)}
          <div className="px-3 pt-4 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Отметки</div>
          {entry('seed')}
          {entry('boundary')}
          <div className="px-3 pt-4 pb-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Связи</div>
          <div className="flex flex-col gap-2 px-3 py-2 text-[13.5px] leading-snug">
            <p>
              <span className="font-semibold">Стрелка</span> — направление перевода: от отправителя к получателю. Толщина — сумма за июль.
            </p>
            <p>
              <span className="font-semibold">Размер узла</span> — приоритет проверки (<span className="font-mono">priority_score</span>).
            </p>
          </div>
        </div>
      </SheetContent>
    </Sheet>
  )
}
