---
type: runbook
owner: Иван
status: active
updated: 2026-09-23
tags: [hackalem, граф-денег, метрики, валидация, без-разметки]
related: ["[[related_work_2026-09-23]]", "[[hypothesis_check_2026-09-23]]", "[[execution_plan_2026-09-23]]", "[[ds_system_design_2026-09-23]]"]
---

# Метрики и проверка качества без разметки

Меток ролей в данных нет, поэтому качество выгрузки проверяется тремя способами: инварианты схемы и сумм (результат либо верен, либо нет), устойчивость к произвольным решениям (seed, порог, шум) и сравнение со случайным контролем (случайное изъятие, перестановка дат). Код проверок: `pipeline/metrics.py`, отдельный модуль без импорта `backend` и без зависимости от способа получения CSV. Он читает три parquet организаторов, три CSV схемы ТЗ и, если есть, `run_meta.json` рядом с ними, пишет только файл `--report` и печатает таблицу. Эталон приоритета не реализован в модуле заново: он вызывает функции пайплайна (`load.load` → `features.compute` → `run._temporal_features` → `priority.v1`) и сверяет результат с CSV, так что формула живёт в одном месте. Имена признаков, колонок и ключей здесь те же, что в CSV пайплайна; их синонимы в `related_work`, плане и коде, формулы и маски собраны в глоссарии `ds_system_design_2026-09-23.md` §8.

```bash
python3 -m pipeline.metrics --data task/data --out outputs --report outputs/metrics.json --perm 1000 --seed 42   # или make metrics
# проверка детерминизма: второй прогон пайплайна в другой каталог, затем
python3 -m pipeline.metrics --data task/data --out outputs --report outputs/metrics.json --compare scratch/run2
```

Код возврата 1, если провалена обязательная проверка. Отчёт пишется всегда: если модуль падает, в `metrics.json` попадает обязательная проверка `metrics_crash` с текстом исключения, код возврата 1. Время на ноутбуке (Python 3.11.4, pandas 2.3.3, networkx 3.4.2, `--perm 1000`, выгрузка v1): 3,5 с внутри модуля, из них 1,0 с эталон пайплайна (точный betweenness), 1,1 с шум ±5 % (20 пересчётов `priority.v1`), 0,7 с перестановки, 0,35 с сравнение с dummy; 4,1 с вместе с запуском Python. Норматив модуля 10 с.

Каждая проверка в `metrics.json` лежит в массиве `checks` как `{group, name, required, ok, value, threshold, note}`. `ok = null` означает информационную метрику или проверку, которая не запускалась. Статусы в таблице: OK, FAIL (обязательная провалена), WARN (необязательная провалена), INFO.

## Группа а. Метрики узла и графа, которые считает пайплайн

Эти величины считает `pipeline/` (features.py, clusters.py, temporal.py, roles_v1.py, priority.py). `metrics.py` сверяет те из них, что лежат колонками в CSV: признаки — с parquet (`features_match_parquet`), `priority_raw`, `priority_score`, `n_terms_above_p95`, `in_queue` — с повторным расчётом функциями пайплайна (`priority_raw_matches_reference`). Обозначения: G — направленный граф пар из `edges.parquet`, U — ненаправленная проекция с весом пары sum(A→B) + sum(B→A). Определения признаков не дублируются: колонка «Определение» ниже сокращена до формулы, полный текст и синонимы — глоссарий `ds_system_design` §8.

| Метрика | Определение и формула | Единицы | Артефакты обхода | Кому служит | Где отчитывается |
|---|---|---|---|---|---|
| `in_deg`, `out_deg` | число разных плательщиков и получателей в G | плательщики, получатели | у 444 узлов depth=4 без исходящих `out_deg = 0` по построению обхода, в скоре вклады out_kzt, out_deg, pass_kzt обнуляются (`rules.BOUNDARY_ZERO_TERMS`); у всех 81 seed входы неполны (обход только по исходящим); 12 seed видны только как получатели, 19 без рёбер | роли consolidator, distributor, coordinator; скор | колонки CSV (опц.), карточка узла |
| `in_kzt`, `out_kzt` (`in_sum_kzt`, `out_sum_kzt` в related_work) | сумма `sum_kzt` входящих и исходящих рёбер | KZT | как выше; входы seed видны только от узлов выгрузки | скор, evidence | карточка, evidence |
| `in_tx`, `out_tx` | число переводов (`n_tx`) | переводы | как выше | карточка | карточка |
| `pass_kzt` | min(in_kzt, out_kzt) | KZT | 0 у 444 граничных узлов глубины 4 и у изолятов (`features.py`); маски у seed нет: у 27 seed есть вход и выход, входы неполны по построению обхода, это названо в evidence флагом `seed_inflow_incomplete` | скор, текст transit | evidence |
| `pass_ratio` (в CSV пайплайна `pass_through`) | pass_kzt / max(in_kzt, out_kzt), 0 без рёбер | доля 0–1 | как у pass_kzt | текст evidence для transit (pass_ratio ≥ 0,8 и pass_kzt ≥ 5 000 KZT); правило роли — out/in 0,8–1,2 | evidence, `features_match_parquet` (±1e−3) |
| `betweenness` | `nx.betweenness_centrality(G, weight=None, normalized=True)`, точный расчёт | доля путей 0–1 | обрыв на depth=4 занижает значения у узлов глубины 3–4 | coordinator, скор | колонка `betweenness`, карточка |
| `n_seed_upstream` | число seed, из которых узел достижим по направленным путям | seed | seed без рёбер (19) не дают путей | coordinator, скор, гипотеза кластера | колонка, карточка |
| `fast_transit_flag` | ≥2 пар «вход A→B, выход B→C» 1-к-1, A≠C, выход/вход 0,8–1,2, лаг 0–2 дня | 0/1 | внутри дня порядок неизвестен; depth=4 без выходов флаг не получают | скор с весом 1,0 (`FAST_TRANSIT_WEIGHT`), роль transit, evidence | evidence, `metrics.json` → `temporal_fast_transit_permutation` |
| статус хронологии пары | «вход раньше выхода» / «тот же день, порядок неизвестен» / «выход раньше входа» | категория | дневная точность дат | только карточка, без веса | карточка топ-20 и искомого gid |
| вклад слагаемого c_j | −ln p_j(x), p_j(x) = доля узлов со значением ≥ x; ноль даёт 0 | безразм., 0…ln 2248 ≈ 7,7 | у граничных узлов глубины 4 c_out_kzt = c_out_deg = c_pass_kzt = 0 | priority, два крупнейших вклада в evidence | evidence, `metrics.json` → `feature_quantiles`, README |
| сырой скор `priority_raw` | Σ c_j по семи слагаемым `rules.SCORE_TERMS` (in_kzt, out_kzt, in_deg, out_deg, betweenness, pass_kzt, n_seed_upstream) + 1,0 · fast_transit_flag | безразм., 0…41,2 на выгрузке v1; потолок 7·ln 2248 + 1 ≈ 55,0 | маски выше | ранжирование | README, колонка `priority_raw` |
| `priority_score` (v1) | priority_raw / max(priority_raw) (`priority.py`) | 0–1 | — | ранжирование, top_nodes | CSV, экран |
| `n_terms_above_p95`, `in_queue` | число слагаемых с вкладом c_j ≥ −ln 0,05 ≈ 2,996 (`rules.TERM_P95_CONTRIBUTION`, признак в верхних 5 %); in_queue = 1 при ≥ 2 (`QUEUE_MIN_TERMS_ABOVE_P95`) | шт.; 0/1 | маски скора | очередь проверки; на выгрузке v1 — 165 узлов из 2 248 | CSV, `run_meta.n_in_queue`, `queue_rule_consistent`, `queue_count_matches_run_meta` |
| `priority_score` (v0) | 0,5·pct_rank(PageRank, вес sum_kzt, α = 0,85) + 0,4·pct_rank(in_deg + out_deg) + 0,1·is_seed | 0–1 | 444 узла depth=4 без выхода копят PageRank | запасная сдача v0 | CSV, README |
| `role_score` | сила поддержки правила, не вероятность: у назначенной роли — среднее по условиям сработавшей ветки, где числовое условие даёт перцентильный ранг значения среди 2 248 узлов (0–1), булево — 1; у peripheral — 1 − максимум такой поддержки по остальным ролям (`roles_v1.py`) | 0–1 | у depth=4 роль terminal запрещена (`terminal_not_truncated`) | цвет роли, карточка | CSV, экран |
| `cluster_id` | Louvain на U, resolution 1,0, seed 42, разрезание несвязных, изоляты отдельно, id по (−размер, min gid) | id | 19 изолятов → 19 одноузловых кластеров | clusters.csv, экран | CSV |
| `sum_kzt_internal` | сумма направленных рёбер G с обоими концами в кластере | KZT | проходящие деньги учитываются на каждом звене | гипотеза кластера | clusters.csv |
| модулярность Q, число сообществ | Q = (1/2m)·Σ_ij [w_ij − γ·k_i·k_j/(2m)]·δ(c_i, c_j); w — вес U (KZT в обе стороны), k — взвешенная степень, γ = 1,0; `nx.community.modularity(U, parts, weight="weight")` | безразм., −0,5…1; шт. | — | README, устойчивость | `metrics.json` → `cluster_modularity`, README «Кластеры» |

Правило очереди (`rules.py`, `priority.py`): узел в очереди проверки, если не меньше 2 из 7 слагаемых скора лежат в верхних 5 % по своему признаку. Ранжирование от очереди не зависит, топ-50 строится по `priority_raw`. На выгрузке v1 в очереди 165 узлов (7,3 %), распределение `n_terms_above_p95`: 0 — 1 894, 1 — 189, 2 — 75, 3 — 52, 4 — 18, 5 — 11, 6 — 9; все 20 узлов топ-20 в очереди. Сумма priority_raw ≥ 6,0 (`run_meta.threshold_raw`, `threshold_score`) остаётся справочным числом и очередью не является: семь слагаемых коррелируют, и порог суммы набирают 681 узел (30,3 %) за счёт многих средних вкладов.

## Группа б. Метрики валидации результата

Обязательные проверки (FAIL даёт код возврата 1) отмечены «да». Ключ — `name` в `metrics.json`.

| Ключ | Что проверяет | Порог | Единицы | Обяз. | Где отчитывается |
|---|---|---|---|---|---|
| `files_present` | три CSV на месте, sha256 каждого | 3 файла | файлы | да | `metrics.json` → checks |
| `csv_parse` | CSV читается (лишняя запятая без кавычек, пустой файл, не UTF-8 дают FAIL) | 3 файла | файлы | да | `metrics.json` → checks |
| `schema_{nodes_roles,clusters,top_nodes}_columns` | колонки схемы ТЗ; лишние допустимы и перечисляются | нет пропусков | колонки | да | `metrics.json` → checks |
| `schema_nodes_roles_dtypes` | gid — целое ≤ 19 цифр в пределах int64, читается строкой и переводится в int без float; при битом gid в `value` три примера записи; скоры числа без NaN, `cluster_id` целое | все 0 | строки | да | `metrics.json` → checks |
| `coverage_nodes` | 2 248 строк, множество gid совпадает с `nodes.parquet` | 0 пропусков, 0 чужих | строки | да | `metrics.json` → checks |
| `gid_unique` | дубли gid | 0 | строки | да | `metrics.json` → checks |
| `role_vocabulary` | роль из шести ролей ТЗ | 0 чужих | роли | да | `metrics.json` → checks |
| `role_distribution` | доли ролей; санити-граница: одна роль ≤ 85 %, ролей ≥ 3 | см. порог | доля 0–1 | нет | README «Критерии ролей и пороги» |
| `terminal_not_truncated` | terminal у узла depth=4 с `out_deg = 0` (выхода не видно по построению обхода) | 0 | узлы | да | `metrics.json` → checks |
| `role_structure_consistency` | consolidator с `in_deg < 2`, distributor с `out_deg < 2`, transit и coordinator без входа или выхода, terminal без входа, изолят не peripheral | все 0 | узлы | нет | `metrics.json` → checks |
| `role_score_range`, `priority_score_range` | значения в [0;1] | 0 вне диапазона | строки | да | `metrics.json` → checks |
| `evidence_format` | непусто, ≤ 200 символов, есть цифра, без перевода строки, без префикса mock (план §3.3) | все 0 | строки | да | `metrics.json` → checks |
| `evidence_mentions_boundary` | у 444 узлов на границе выгрузки evidence называет границу (depth=4, «граница», «колено», «обрыв», «выгрузка») | все | узлы | нет | `metrics.json` → checks |
| `top_min_rows` | строк в top_nodes | ≥ 20 | строки | да | `metrics.json` → checks |
| `top_rank_sorted` | rank = 1…n, priority не возрастает и числовой | — | строки | да | `metrics.json` → checks |
| `top_gid_in_nodes` | gid из top есть в nodes_roles, без дублей | все 0 | строки | да | `metrics.json` → checks |
| `top_matches_nodes` | роль и priority в top совпадают с nodes_roles (допуск 1e−6; нечисловой priority — расхождение) | все 0 | строки | да | `metrics.json` → checks |
| `top_is_topk_by_priority` | top — первые k по priority в nodes_roles (равенство по gid) | пересечение = k | узлы | нет | `metrics.json` → checks |
| `top_why_nonempty` | why непуст; пустое значение: FAIL (план §3.3) | 0 | строки | да | `metrics.json` → checks |
| `top_why_format` | why с цифрой, ≤ 200 | все 0 | строки | нет | `metrics.json` → checks |
| `schema_clusters_dtypes` | cluster_id, n_nodes, n_seed целые; sum_kzt_internal число | все 0 | строки | да | `metrics.json` → checks |
| `cluster_ids_consistent` | cluster_id у каждого узла, одна строка на id в clusters.csv, множества совпадают | все 0 | кластеры | да | `metrics.json` → checks |
| `cluster_n_nodes` | n_nodes = пересчёт по nodes_roles; Σ = 2 248 | 0 расхождений | кластеры | да | `metrics.json` → checks |
| `cluster_n_seed` | n_seed = пересчёт; Σ = 81 | 0 расхождений | кластеры | да | `metrics.json` → checks |
| `cluster_sum_kzt_internal` | каждая строка = пересчёт по edges (±1 KZT); каждая и сумма ≤ оборота 365 890 012 KZT | — | KZT | да | `metrics.json` → checks |
| `cluster_top_gids_subset` | каждый gid из top_gids лежит в своём кластере; пустой список: FAIL | 0 | gid | да | `metrics.json` → checks |
| `cluster_hypothesis_nonempty` | гипотеза непуста; пустое значение: FAIL (план §3.3) | 0 | кластеры | да | `metrics.json` → checks |
| `cluster_hypothesis_format` | гипотеза содержит число | все 0 | кластеры | нет | `metrics.json` → checks |
| `cluster_connected_in_U` | подграф U каждого кластера связен | 0 несвязных | кластеры | да | `metrics.json` → checks |
| `determinism_two_runs` | sha256 трёх CSV совпадают со вторым прогоном (`--compare`) | все True | файлы | да, если задан `--compare` | README «Воспроизводимость» |
| `cluster_matches_reference` | AMI и ARI выгрузки против эталонного Louvain seed 42; 1,0 ожидается, если U строится по возрастанию gid и в порядке `edges.parquet` (ds_system_design §3); при другом порядке вставки узлов 0,93–0,96, как между разными seed, и это не ошибка пайплайна | INFO | безразм. (≤ 1, около 0 при случайном совпадении) | нет | README «Кластеры» |
| `cluster_stability_seed` | эталонный Louvain на U с seed 42/1/7: AMI и ARI попарно; плюс AMI/ARI выгрузки против каждого | AMI между seed ≥ 0,90 | безразм. (≤ 1, около 0 при случайном совпадении) | нет | README «Кластеры» |
| `cluster_stability_resolution` | resolution 0,8 и 1,2 против 1,0 (seed 42): число сообществ, AMI, ARI | AMI ≥ 0,85 | безразм.; шт. | нет | README «Кластеры» |
| `top20_noise_5pct` | 20 повторов шума U(0,95; 1,05) на каждый перевод; суммы, pass_kzt и быстрый транзит пересчитываются, затем `priority.v1` пайплайна; доля пересечения топ-20 | среднее ≥ 0,80 | доля 0–1 | нет | README «Устойчивость» |
| `top20_ablation` | топ-20 эталона пайплайна без каждого из семи слагаемых c_j и без флага по очереди | пересечение ≥ 0,70 | доля 0–1 | нет | README «Устойчивость» |
| `role_threshold_sensitivity` | доля узлов, меняющих роль при сдвиге одного порога на соседнюю ступень лестницы квантилей P50/P75/P90/P95/P97,5/P99/P99,5 (среди ненулевых значений); полоса transit 0,1 и 0,3 вместо 0,2 | max ≤ 10 % | доля узлов 0–1 | нет | README «Критерии ролей и пороги» |
| `temporal_fast_transit_permutation` | `pipeline.temporal_check.run_check`, статистика fast_transit (при ошибке импорта или `--temporal-impl own` — своя реализация): число узлов с флагом: наблюдаемое, среднее и SD контроля, p = (1 + #нуль ≥ набл.)/(N + 1) при двух нулях: глобальная перестановка столбца дат и перестановка дат внутри отправителя; N ≥ 100, по умолчанию 1 000; при N < 99 статус INFO, порог 0,01 недостижим | p ≤ 0,01 при обоих | узлы; p безразм. | нет | README, абзац о перестановочном контроле |
| `features_match_parquet` | дополнительные колонки CSV против parquet: степени, число переводов, depth, is_seed, truncated_by_depth точно; in_kzt, out_kzt, pass_kzt = min(in, out) ±0,01 KZT; pass_through = min/max ±1e−3; betweenness ±1e−6 | 0 расхождений | строки | нет | `metrics.json` → checks |
| `priority_raw_matches_reference` | колонки `priority_raw`, `priority_score`, `n_terms_above_p95`, `in_queue` против повторного расчёта функциями пайплайна на parquet; в `value` по каждой колонке число строк с расхождением, максимум \|Δ\| и пример gid | \|Δ\| ≤ 1e−3 по скорам, 0 по очереди | строки | да (при колонке `priority_raw`) | `metrics.json` → checks |
| `queue_count_matches_run_meta` | число строк in_queue = 1 в nodes_roles.csv против `run_meta.n_in_queue` | равны | узлы | нет | `metrics.json` → checks |
| `queue_rule_consistent` | при колонках `in_queue` и `n_terms_above_p95`: in_queue = 1 ⇔ n_terms_above_p95 ≥ `run_meta.queue_min_terms_above_p95` (без ключа 2); в `value` число узлов в очереди и распределение n_terms_above_p95 | 0 | строки | нет | `metrics.json` → checks, README «Очередь проверки» |
| `pipeline_runtime` | `elapsed_s`, метод и стадии (`stages_s`) из `run_meta.json` пайплайна | ≤ 300 с | с | нет | README «Воспроизводимость» |
| `metrics_crash` | появляется только при падении модуля: тип и текст исключения | — | — | да | `metrics.json` → checks |
| `baselines_run` | вызов `pipeline.baselines.run_baselines(data, out, seed)`; результат целиком в ключе `baselines` отчёта, ошибка — в `note` без падения модуля | — | — | нет | `metrics.json` → baselines |
| `timing_s` (не проверка) | время стадий самого `metrics.py` | — | с | — | `metrics.json` |

Оговорки к реализации:

- AMI считается с поправкой на ожидаемую взаимную информацию (Vinh и др., 2010), среднее арифметическое энтропий, как `adjusted_mutual_info_score` в scikit-learn. ARI по Hubert и Arabie: ARI = (Σ_ij C(n_ij,2) − E)/(½(Σ_i C(a_i,2) + Σ_j C(b_j,2)) − E), E = Σ_i C(a_i,2)·Σ_j C(b_j,2)/C(n,2). Своя реализация на numpy/scipy, без scikit-learn.
- Флаг быстрого транзита: «существует сопоставление 1-к-1 из ≥ 2 пар». По умолчанию перестановочный контроль берётся из `pipeline/temporal_check.py` (`run_check(tx_df, n_perm, seed)`, строки со статистикой fast_transit, нули global и within_sender). Своя векторная реализация (равносильная форма «≥ 2 разных входа и ≥ 2 разных выхода среди допустимых пар») остаётся запасной: `--temporal-impl own` или ошибка импорта, причина пишется в `note`.
- Шум и ablation считаются на эталоне пайплайна (`priority.v1`), поэтому совпадают по формуле с выгрузкой. Чувствительность ролей к порогам пока считается на правилах заглушки v0 (coordinator in ≥ 3 и out ≥ 5; distributor out ≥ 10; consolidator in ≥ 3; transit out/in 0,8–1,2; terminal вход без выхода при depth < 4), а не на `roles_v1.py`.

## Группа в. Метрики ценности для README и демо

| Ключ | Определение | Единицы | Где отчитывается |
|---|---|---|---|
| `value_removal_topN` | изъять N = 10/20/50 узлов по порядку priority_score из CSV; LCC — крупнейшая слабая компонента G после изъятия (узлы), `turnover_left` — доля оборота на рёбрах без изъятых узлов. Сравнение: случайный порядок (медиана 20 повторов, seed 42), betweenness, оборот (вход + выход) | узлы; доля 0–1 | README «Ценность» и «Устойчивость» (§8 ТЗ) |
| `value_queue_share` | доля и число узлов с in_queue = 1, сколько из топ-20 по priority_score в очереди, текст `run_meta.queue_rule` | доля 0–1; узлы | README «Очередь проверки» |
| `feature_quantiles` | P50/P75/P90/P95/P99 семи слагаемых скора по всем 2 248 узлам и среди ненулевых (значения эталона пайплайна) | единицы признака | README, таблица перцентилей |
| `cluster_modularity` | Q выгрузки и эталонного Louvain seed 42 на явной U; эталон 0,8595 | безразм. | README «Кластеры» |
| `value_manual_3gid` | три gid, выбранных по seed; ручной чек по шаблону ниже | gid | `docs/acceptance.md`, демо |

Базовые числа изъятия на тех же данных (не зависят от CSV): исходная LCC 1 877 узлов; по betweenness LCC 1 567 / 1 257 / 921 и остаток оборота 85,2 / 75,7 / 66,1 %; по обороту 1 466 / 1 376 / 1 034 и 71,4 / 62,3 / 43,7 %; по priority_score выгрузки v1 1 456 / 1 243 / 930 и 74,5 / 64,9 / 48,4 %; случайно медиана 1 863,5 / 1 845 / 1 792 и 99,3 / 98,4 / 95,4 %. Строки по betweenness и обороту совпадают с related_work, блок 4; медиана случайного изъятия отличается на 2–3 узла (там 1 866 / 1 848 / 1 790) из-за другой последовательности случайных чисел.

Шаблон ручного чека «gid за минуту» (засекать время от ввода gid в поиск):

| Поле | Что сверить | Результат |
|---|---|---|
| gid | взят из `value_manual_3gid` | |
| роль и role_score | по карточке | |
| правило роли | какое условие выполнено, с порогом из README | да / нет |
| числа evidence | совпадают с карточкой (плательщики и получатели, KZT, перцентили) | да / нет |
| ограничения | depth=4, seed без входов, изолят названы, если применимы | да / нет |
| кластер | cluster_id и гипотеза кластера открываются с карточки | да / нет |
| время | секунды до ответа «почему этот узел здесь» | ≤ 60 |

## Пример отчёта: выгрузка v1

Прогон 23.09.2026 на `outputs/` (v1: роли consolidator 144, coordinator 54, distributor 29, peripheral 926, terminal 1 034, transit 61; 89 кластеров; топ-50; max priority_raw 41,2036), `--perm 1000 --seed 42`. Отчёт — `outputs/metrics.json`. Итог: 51 проверка, обязательных провалов 0, одно предупреждение, код возврата 0; 3,5 с внутри модуля.

| гр | проверка | статус | значение |
|---|---|---|---|
| b | схема, покрытие, gid, словарь ролей, evidence, top, кластерные суммы (27 проверок) | OK | 2 248 строк, 0 расхождений; evidence у 444 из 444 граничных узлов называет границу |
| b | `features_match_parquet` | OK | 0 расхождений по 12 колонкам |
| b | `priority_raw_matches_reference` | OK | 0 строк с расхождением по `priority_raw`, `priority_score`, `n_terms_above_p95`, `in_queue`; max \|Δ\| 0 |
| b | `queue_rule_consistent`, `queue_count_matches_run_meta` | OK | в очереди 165 узлов, в `run_meta.n_in_queue` 165 |
| b | `cluster_stability_seed` | OK | сообществ 91 / 86 / 92 при seed 42 / 1 / 7; AMI между seed 0,930–0,960; выгрузка против Louvain seed 42 AMI 0,951 |
| b | `top20_noise_5pct` | OK | среднее пересечение топ-20 0,965, минимум 0,95 (20 повторов) |
| b | `top20_ablation` | OK | минимум 0,80 (без out_deg); без остальных слагаемых и флага 0,85–0,90 |
| b | `role_threshold_sensitivity` | WARN | правила v0: consolidator in ≥ 3 → ≥ 2 меняет роль у 10,5 % узлов; остальные сдвиги 0,3–3,8 % |
| b | `temporal_fast_transit_permutation` | OK | 54 узла; при случайных датах 34,1 (SD 3,5) и 38,2 (SD 3,6), p = 0,001 в обоих нулях |
| c | `cluster_modularity` | INFO | выгрузка 0,8589 (89 кластеров), эталонный Louvain 0,8595 (91) |
| c | `value_removal_topN` | OK | изъятие топ-20: LCC 1 243 из 1 877, остаток оборота 64,9 %; случайно 1 845 и 98,4 % |
| c | `value_queue_share` | INFO | 165 узлов (7,3 %); из топ-20 в очереди 20 |
| c | `baselines_run` | OK | 10 строк итога, 0 предупреждений; числа в разделе ниже |

Предупреждение относится к правилам заглушки v0, на которых пока считается чувствительность ролей: порог in_deg ≥ 3 стоит на P95, соседняя ступень in_deg ≥ 2 (P90) переводит в consolidator 10,5 % узлов. Для `roles_v1.py` эта проверка не пересчитана.

## Сравнение с dummy-заменителями

Меток ролей и «правильного» приоритета нет, поэтому accuracy не считается. Каждый выход пайплайна сравнивается с простым заменителем на измеримых прокси-исходах. Сравнение отвечает на вопрос «даёт ли наш шаг что-то сверх тривиального правила», но не на вопрос «верна ли роль». Код: `pipeline/baselines.py`, ничего не пишет, кроме `--report`; из кода `run_baselines(data_dir, out_dir, seed=42, n_random=20, role_fn=None) -> dict`. `metrics.py` вызывает его и кладёт результат в ключ `baselines`; отдельно — `make baselines` (`outputs/baselines.json`).

| Блок | Dummy | Прокси-исход | Лучше |
|---|---|---|---|
| priority | случайный порядок; in_kzt + out_kzt; in_deg + out_deg; PageRank стартового кода; все seed первыми | снятый оборот (Σ sum_kzt рёбер, инцидентных изъятым, / 365 890 012 KZT); LCC после изъятия; затронутые seed-ветви из 81; доля depth 4 среди изъятых | больше; меньше; больше; меньше |
| roles | «все peripheral»; «по одному признаку» (terminal при out_deg = 0 без учёта depth, distributor при out_deg ≥ 10, consolidator при in_deg ≥ 3) | terminal на depth 4 | меньше |
| clusters | слабосвязные компоненты (WCC); случайное разбиение тех же размеров | модулярность на U; доля внутреннего оборота | больше |
| temporal | те же переводы со случайными датами, 200 перестановок, два нуля | число узлов с флагом, p | больше |

Против случайного dummy «лучше» и «хуже» засчитываются только вне полосы 5–95 % по 20 повторам (seed 42).

Числа на выгрузке v1 (из `outputs/metrics.json` → `baselines`), изъятие топ-20; для случайных dummy — медиана:

| Метод | Снятый оборот | LCC (до изъятия 1 877) | Seed-ветви из 81 | Доля depth 4 |
|---|---|---|---|---|
| наш priority_score | 35,1 % | 1 243 | 17 | 0 |
| случайный | 1,6 % | 1 845 | 14 | 0,13 |
| оборот | 37,7 % | 1 376 | 13 | 0 |
| степень | 30,3 % | 1 188 | 12 | 0 |
| PageRank | 7,2 % | 1 834 | 17 | 0 |
| seed первыми | 4,1 % | 1 797 | 32,5 | 0 |

- Priority против случайного порядка и PageRank лучше по снятому обороту и LCC при N = 10, 20, 50. Ранжирование по обороту снимает больше оборота (при N = 20 37,7 % против 35,1 %), но оставляет LCC 1 376 против 1 243 и задевает 13 seed-ветвей против 17. Ранжирование по степени сильнее режет LCC, но снимает меньше оборота. «Seed первыми» по построению задевает больше seed-ветвей.
- Роли: terminal на depth 4 — 0 у нас, 444 у dummy по одному признаку. Энтропия ролей 1,648 бита против 1,217, доля не peripheral 0,588.
- Кластеры: Q на U 0,859 против 0,125 у WCC и −0,007 у случайного разбиения; доля внутреннего оборота 0,905 (у WCC 1,0 по построению).
- Быстрый транзит: 54 узла против 33,7 и 38,1 при случайных датах, p = 0,005 (минимум при 200 перестановках); совпадение с эталонным определением флага, Жаккар 1,00.

«Лучше dummy» не значит «правильно»: часть dummy напрямую оптимизирует свой прокси (оборот — снятый оборот, степень — LCC, seed первыми — seed-ветви), поэтому смотреть надо на то, чем их выигрыш оплачен в других столбцах. Шум ±5 % для ролей без `--role-fn` не считается.

Отрицательная проверка модуля (на версии до перехода на эталон пайплайна; проверки схемы с тех пор не менялись): 26 поломок на копии заглушки, где префикс `mock` в evidence и why заменён, чтобы исходная копия проходила с кодом 0. Все 25 поломок дают код 1 с отчётом и без traceback; перестановка строк nodes_roles даёт код 0, как и должно. Примеры: удалённая строка → `coverage_nodes`, `cluster_n_nodes`, `cluster_sum_kzt_internal`; один gid в виде `1.000000001e+17` и 19-значный gid вне int64 → `schema_nodes_roles_dtypes`, `coverage_nodes` и кластерные суммы, остальные 2 247 gid читаются точно; все gid во float → девять обязательных провалов; evidence с переводом строки → `evidence_format`; пустые why и hypothesis → `top_why_nonempty`, `cluster_hypothesis_nonempty`; пустой top_gids → `cluster_top_gids_subset`; дробный cluster_id в clusters.csv → `schema_clusters_dtypes`, `cluster_ids_consistent`; «0,97» в top_nodes → `top_rank_sorted`, `top_matches_nodes`; лишняя запятая без кавычек → `csv_parse`. Копия пакета с temporal_check.py, который разбирает argv при импорте: код 0 и полный отчёт, в `note` «temporal_check недоступен: SystemExit», перестановки считает своя реализация.
