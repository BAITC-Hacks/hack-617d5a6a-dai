import type { ReactElement } from 'react'
import { RoleIcon } from '@/components/role-icon'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { useRoleInfo } from '@/lib/graph-data'
import type { Role } from '@/lib/roles'

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

/** Пункт легенды в шапке: значок + подпись, подсказка по наведению и фокусу. */
export function LegendEntry({ item }: { item: LegendItem }) {
  const roleInfo = useRoleInfo()
  const label = isRole(item) ? roleInfo(item).title : LEGEND[item].title
  return (
    <LegendTooltip item={item}>
      <button
        type="button"
        className="flex cursor-help items-center gap-[7px] rounded-sm text-[13.5px] font-medium whitespace-nowrap outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <LegendIcon item={item} />
        {label}
      </button>
    </LegendTooltip>
  )
}
