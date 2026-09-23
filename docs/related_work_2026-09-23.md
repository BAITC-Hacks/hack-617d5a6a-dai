# Смежные работы и решения по методам

Дата: 23.09.2026, 15:20 (Asia/Almaty). Связанные документы: `hypothesis_check_2026-09-23.md` (итог проверки временной гипотезы, её решения учтены ниже), `deep_research_request_2026-09-23.md` (срез данных и вопросы), `temporal_research.md`.

## Зачем и как искали

Кейс требует ранжировать 2 248 клиентов без меток ролей, без обучения, без внешних данных, за <5 минут на CPU и объяснить каждую позицию числами. Искали опубликованные методы по трём направлениям: интерпретируемые графовые скоры для AML, временные шаблоны на переводах с точностью до дня и способы обосновать порог без разметки. Каждого кандидата оценивали по трём вопросам: ложится ли на networkx/pandas за ≤60 минут, объясним ли результат аналитику одним числом, совместим ли он с артефактами данных (обход только по исходящим от seed, 444 узла глубины 4 без исходящих, 19 seed без рёбер). Ссылки сверены с первоисточниками: 43 проверки по 33 источникам, 41 совпала полностью, 2 исправлены (страница networkx подтверждает только Dugué и Perez 2015; связка GraphWave/struc2vec/Digraphwave покрыта одной ссылкой на GraphWave), непроверяемых нет. Дубли из разных направлений объединены в одну строку.

## Таблица кандидатов

| Подход | Работа (ссылка) | Что даёт | Где в нашем пайплайне | Решение |
| --- | --- | --- | --- | --- |
| Один скор из хвостовых вероятностей признаков | ECOD, Li и др., IEEE TKDE ([arXiv 2201.00382](https://arxiv.org/abs/2201.00382)) | Сумма −ln хвостов по каждому признаку; вклад каждого признака виден отдельно, параметров нет | `priority_score`, порог, `evidence` | берём сейчас |
| Шаблон сквозного перевода с сопоставлением 1-к-1 | Climaco, 2026 ([arXiv 2609.20737](https://arxiv.org/abs/2609.20737)) | Вход и выход близкой суммы в окне времени; один входящий перевод не засчитывается дважды | временной слой, роль transit, `evidence` | берём сейчас (форма из проверки гипотезы) |
| Временные мотивы в окне δ | Paranjape, Benson, Leskovec, WSDM 2017 ([arXiv 1612.09259](https://arxiv.org/abs/1612.09259)) | Формальное определение цепочки «вход → выход за ≤δ дней» | временной слой (формальная основа блока 2) | берём сейчас как определение; полный каталог мотивов в README |
| Перестановочные контроли для временных сетей | Gauvin и др., SIAM Review 2022 ([arXiv 1806.04032](https://arxiv.org/abs/1806.04032)) | Перемешивание дат при фиксированных рёбрах даёт нуль для временного признака и объяснимый порог | README, порог флага быстрого транзита | берём сейчас |
| Сквозная сумма посредника | FlowScope, Li и др., AAAI 2020 ([ссылка](https://ojs.aaai.org/index.php/AAAI/article/view/5906)) | «Прошло много, осталось мало»: min(вход, выход) в KZT | признак `pass_kzt` для роли transit и скора | берём упрощение; полный алгоритм в README |
| Словарь типологий отмывания | AMLworld, Altman и др., NeurIPS 2023 Datasets ([arXiv 2306.16424](https://arxiv.org/abs/2306.16424)) | Имена fan-in, fan-out, gather-scatter, scatter-gather, cycle, stack для правил ролей | роли, `evidence`, README | берём имена; датасет не используется |
| Устойчивость к удалению узлов | Morone, Makse, Nature 2015 ([arXiv 1506.08326](https://arxiv.org/abs/1506.08326)) | Базовая линия: удаление топ-N по скору против случайного удаления | README (ценность), §8 устойчивость | берём таблицу; collective influence в README |
| Ориентированная модулярность и устойчивость по seed | Dugué, Perez, 2015, реализация в networkx ([документация](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html)) | Сравнение разбиений проекции и DiGraph, повторы с разными seed | кластеры, README (воспроизводимость) | берём проверку |
| Гарантия связности сообществ | Leiden, Traag и др., Sci. Rep. 2019 ([arXiv 1810.08473](https://arxiv.org/abs/1810.08473)) | Louvain может выдавать несвязные сообщества; в networkx 3.4.2 Leiden нет | кластеры: проверка `is_connected` по кластеру | проверку берём; Leiden в README |
| Риск смёрфинга по блокам окрестности второго порядка | GARG-AML, Deprez и др., 2025 ([arXiv 2506.04292](https://arxiv.org/abs/2506.04292)) | Один скор в [−1; 1] на счёт по плотности блоков матрицы смежности | кандидат на признак скора после обязательных пунктов | упоминаем |
| Обзор сетевой аналитики для AML | Deprez и др., 2024, ред. 2025 ([arXiv 2405.19383](https://arxiv.org/abs/2405.19383)) | Большинство работ опирается на правила и ручные признаки; предупреждение о метриках на синтетике | README (почему правила, а не нейросеть) | упоминаем |
| Триаж алертов поверх правил | Eddin и др., 2021/2022 ([arXiv 2112.07508](https://arxiv.org/abs/2112.07508)) | Постановка «правила дают кандидатов, скор ранжирует очередь» | README (ценность: доля проверок) | упоминаем |
| Скор → вклады → фраза для аналитика | Zhang и др., KDD 2026 MLF workshop ([arXiv 2607.17586](https://arxiv.org/abs/2607.17586)) | Формат вывода: одно число, объявленный порог, топ-вклады признаков | формат `evidence` | упоминаем; сам метод требует меток |
| Потоковые подграфовые признаки | Graph Feature Preprocessor, Blanuša и др., ICAIF 2024 ([arXiv 2402.08593](https://arxiv.org/abs/2402.08593)) | Признаки fan/cycle/scatter-gather на потоке транзакций, бустинг поверх | README (масштабирование, потенциал при появлении меток) | упоминаем |
| GNN для ориентированных мультиграфов | Egressy и др., AAAI 2024 ([arXiv 2306.11586](https://arxiv.org/abs/2306.11586)) | Различает любой направленный шаблон; нужны метки и обучение | README (потенциал) | упоминаем |
| Временные циклы на больших графах | 2SCENT, Kumar, Calders, PVLDB 2018 ([PDF](http://www.vldb.org/pvldb/vol11/p1441-kumar.pdf)) | Перечисление простых временных циклов на миллионах узлов | README (масштабирование §8 циклов) | упоминаем |
| Связанные тензоры для цепочек | CubeFlow, Sun и др., PAKDD 2021 ([arXiv 2103.12411](https://arxiv.org/pdf/2103.12411)) | Учёт времени и суммы в поиске цепочек | README (масштабирование) | упоминаем |
| Граф переводов второго порядка | FaSTMAN, Tariq, Hassani, 2023 ([arXiv 2309.13662](https://arxiv.org/abs/2309.13662)) | Рёбра «вход → выход» как узлы, кластеры по потокам | README (масштабирование) | упоминаем |
| Пути от seed с объяснением | FlowSeries, Capozzi и др., 2025 ([arXiv 2503.15896](https://arxiv.org/abs/2503.15896)) | Банковский прецедент подхода от seed без меток на 80 млн переводов | README (ценность, потенциал) | упоминаем |
| Временной максимальный поток против ложных smurfing-шаблонов | SMoTeF, Shadrooh, Nørvåg, Applied Intelligence 2024 ([ссылка](https://link.springer.com/article/10.1007/s10489-024-05545-4)) | Отсев статических шаблонов, невозможных во времени | README (потенциал) | упоминаем |
| От улики к группе | Clue2Group, Wang, Cao, 2026 ([arXiv 2606.26189](https://arxiv.org/abs/2606.26189)) | Постановка «расширение группы от подозрительных счетов с участием аналитика» | README (потенциал: экран с поиском gid) | упоминаем |
| Сообщества по потокам | Infomap, Smiljanić и др., ACM Computing Surveys 2026 ([arXiv 2311.04036](https://arxiv.org/html/2311.04036v2)) | Учёт направления потока; на обходе от seed дробит ветки (339 модулей против 91) | README (проверка на полных данных) | упоминаем |
| Структурные роли без разметки | RolX, Henderson и др., KDD 2012 ([ссылка](https://research.google/pubs/rolx-structural-role-extraction-mining-in-large-graphs/)) | NMF по рекурсивным признакам; компоненты безымянные, transit не выделяется | README (независимая проверка правил) | упоминаем |
| Кластеризация по мотивам | Benson, Gleich, Leskovec, Science 2016 ([arXiv 1612.08447](https://arxiv.org/abs/1612.08447)) | Счётчики взаимных пар и циклов уже посчитаны (177 взаимных пар, 1 541 цикл ≤6) | карточка узла, если останется время | упоминаем |
| Всплески активности | Kleinberg, KDD 2002 ([PDF](https://www.cs.cornell.edu/home/kleinber/bhs.pdf)) | Автомат для периодов повышенной частоты; у большинства узлов 1–3 перевода | README; заменяется счётом плательщиков за день | упоминаем |
| Пути с неубывающим временем | Kempe, Kleinberg, Kumar, JCSS 2002 ([ссылка](https://www.sciencedirect.com/science/article/pii/S0022000002918295)) | Достижимость с соблюдением порядка дат; при дневной точности близка к статической | README (§8 маршруты) | упоминаем |
| Калибровка правил без меток | Data Programming, Ratner и др., NIPS 2016 ([arXiv 1605.07723](https://arxiv.org/abs/1605.07723)) | Правила как шумные функции разметки; ненадёжно при 6 классах и коррелированных правилах | README (путь к вероятностям ролей) | упоминаем |
| Плотные подграфы против закона Бенфорда | Chen, Tsourakakis, KDD 2022 ([arXiv 2205.13426](https://arxiv.org/pdf/2205.13426)) | Отклонение первых цифр сумм | — | отвергли |
| Самоконтролируемые эмбеддинги | LaundroGraph, Cardoso и др., ICAIF 2022 ([arXiv 2210.14360](https://arxiv.org/abs/2210.14360)) | Эмбеддинги без меток, нужен PyTorch | — | отвергли |
| Hub и authority | HITS, Kleinberg, JACM 1999 ([PDF](https://www.cs.cornell.edu/home/kleinber/auth.pdf)) | Взвешенная версия сосредоточена на 8 hub и 6 authority | — | отвергли |
| Структурные эмбеддинги | GraphWave, Donnat и др., KDD 2018 ([arXiv 1710.10321](https://arxiv.org/abs/1710.10321)) | Векторы структурной идентичности | — | отвергли |
| Пакет для time-respecting paths | pathpy ([GitHub](https://github.com/uzhdag/pathpy)) | Извлечение путей и графы высших порядков | — | отвергли |
| Персонализированный PageRank от seed | TRacer, Wu и др., 2022 ([arXiv 2201.05757](https://arxiv.org/abs/2201.05757)) | Доля потока от заданных адресов | — | отвергли сейчас |

## Берём сейчас

Порядок работ: ближайший коммит пайплайна закрывает обязательные пункты (роли, кластеры, `priority_score`, три CSV, экран графа с поиском) без временного слоя, ориентир 16:00. Затем четыре блока ниже, ≈95 минут работы на двоих: блок 1 и блок 2 параллельно (16:00–16:40), блоки 3–4 и README (16:40–17:20), 40 минут запаса до сдачи. Если к 17:00 обязательные пункты не закрыты, блоки 2–4 снимаются; блок 1 остаётся, он меняет только формулу `priority_score` и занимает 20 минут.

### Блок 1. Один риск-скор из хвостовых вероятностей (ECOD)

- Вход: таблица узлов с признаками `in_sum_kzt`, `out_sum_kzt`, `in_deg` (число разных плательщиков), `out_deg` (число разных получателей), `betweenness` (направленная, точная), `pass_kzt` (блок 3), `fast_transit_flag` (блок 2). У 444 узлов глубины 4 исходящие признаки отсутствуют по артефакту обхода: `out_*` и `pass_kzt` у них не считаются и дают вклад 0.
- Формула: для признака j и значения x хвост p_j(x) = доля узлов со значением ≥ x (равные включаются; нулевое значение даёт p = 1 и вклад 0, поэтому связки рангов на нулях скор не завышают). `priority_score = Σ_j −ln p_j + w · fast_transit_flag`, w = 1,0. Вклад одного признака ограничен сверху ln 2248 ≈ 7,7.
- Порог: 6,0 = 2 · (−ln 0,05). Узел на пороге стоит выше P95 сразу по двум признакам или выше P99,75 по одному. Узлы со скором ≥ 6,0 попадают в очередь проверки; `top_nodes.csv` содержит первые 20 по скору независимо от порога. Флаг с весом 1,0 равен одному признаку на уровне P63 и порог самостоятельно не преодолевает; это соответствует решению о малом весе из проверки гипотезы.
- `evidence`: два признака с наибольшим вкладом, значение и перцентиль, затем флаг. Образец: «скор 8,4 (порог 6,0): сквозная сумма 41,2 млн KZT (P99), 23 получателя (P98); быстрый транзит: 3 пары за 0–2 дня». В README отдельная строка: вклад = −ln(доля узлов с не меньшим значением), таблица перцентилей по каждому признаку.
- Роли не меняются: словарь ТЗ и правила с квантилями остаются, `role_score` считается по ним; `priority_score` живёт отдельной шкалой, как решено командой.
- Минуты: 20 (2 248 строк × 7 признаков, расчёт долей в pandas за доли секунды).

### Блок 2. Быстрый транзит: пары вход → выход 1-к-1 с перестановочным контролем

- Вход: `transactions.parquet`. Для узла B пары (A→B, B→C) с A ≠ C, лагом Δ = день выхода − день входа ∈ [0; 2] и отношением сумм выход/вход ∈ [0,8; 1,2]. Сопоставление 1-к-1: каждый входящий и каждый исходящий перевод участвует не более чем в одной паре; жадный выбор по дате, при остатке времени `networkx.max_weight_matching` с весом −|отношение − 1|.
- Правило: `fast_transit_flag = (число пар ≥ 2)`. Замер из проверки гипотезы: 54 узла против 33,9–38,1 при трёх перестановочных контролях (500–1 000 перестановок дат, p ≤ 0,002); после удаления 97 дублей строк 54 узла, p = 0,001. На уровне узла 26 из 54 флагов появляются в ≥50 % перестановок, поэтому счёт пар как непрерывный признак не берётся, вес флага 1,0.
- Оговорки для README: внутри одного дня порядок переводов неизвестен, лаг 0 означает «в тот же день»; входы узлов глубины 1 видны только от seed; 444 узла глубины 4 признак не получают.
- Вывод в `evidence`: «быстрый транзит: N пар за 0–2 дня, суммы ±20 %». Слова «возмещение», «аванс», «нелинейное время» не используются.
- Дополнительно для карточек топ-20 и искомого gid: JSON пар со статусом хронологии на паре («вход раньше выхода», «тот же день, порядок неизвестен», «выход раньше входа»), без веса в скорах; 38 311 пар строятся за 0,006 с.
- Минуты: 30 (признак 15 + JSON пар 15) и 10 на `pipeline/temporal_check.py` с таблицей перестановочного контроля и абзац README.

### Блок 3. Сквозная сумма и имена типологий

- Вход: `edges.parquet`, агрегаты по узлу. `pass_kzt = min(in_sum_kzt, out_sum_kzt)` для узлов глубины 1–3; `pass_ratio = pass_kzt / max(in_sum_kzt, out_sum_kzt)` для текста. Узлы глубины 4 и seed без рёбер маскируются (у первых нет выходов, у вторых нет входов по построению).
- Порог для текста transit: `pass_ratio ≥ 0,8` и `pass_kzt ≥ 5 000 KZT` (порог данных). Правило роли transit при этом остаётся прежним; `pass_kzt` входит в скор блока 1 как отдельный признак, `pass_ratio` идёт в `evidence`.
- Имена типологий в `evidence` и в таблице README: consolidator — fan-in (сходимость входов); distributor — fan-out (веер выходов); coordinator — gather-scatter (высокий вход и высокий выход одновременно); transit — звено scatter-gather или stack (в данных 797 пар отправитель–получатель с ≥2 разными посредниками); terminal и peripheral — лист без исходящих или узел с одной связью. Образец: «distributor (fan-out): 23 получателя, 41,2 млн KZT исходящих».
- Минуты: 15 на признаки и 10 на таблицу соответствия в README.

### Блок 4. Проверки устойчивости для README

- Кластеры: прогон Louvain на проекции с seed 42, 1, 7 и на DiGraph с ориентированной модулярностью; сравнение по AMI и ARI. Замер: проекция 91 сообщество, Q = 0,847; DiGraph 91 сообщество, Q = 0,859, AMI между ними 0,92; между seed AMI 0,944–0,955, ARI 0,864–0,908; каждый прогон 0,04 с. Плюс `is_connected` по подграфу каждого кластера (число несвязных кластеров в README). 10 минут.
- Ранжирование: таблица «удалили топ-N по `priority_score` → размер крупнейшей слабой компоненты и остаток оборота» для N = 10, 20, 50 против случайного удаления (20 повторов, seed 42) и против удаления по betweenness и по обороту. Базовые числа уже замерены: исходная компонента 1 877 узлов; по betweenness LCC 1 567 / 1 257 / 921 и остаток оборота 85,2 / 75,7 / 66,1 %; по обороту 1 466 / 1 376 / 1 034 и 71,4 / 62,3 / 43,7 %; случайно медиана LCC 1 866 / 1 848 / 1 790. Колонка для нашего скора добавляется после блока 1. Полный расчёт <2 с. 20 минут.
- Куда: README, разделы «ценность» и «устойчивость» (§8 ТЗ), одна фраза в описании кластеров.

### Как блоки складываются в один скор

Компоненты скора: пять статических признаков (входящий и исходящий оборот, число плательщиков и получателей, betweenness), сквозная сумма (блок 3) и бинарный флаг быстрого транзита (блок 2). Каждый вклад читается как «доля узлов с не меньшим значением», порог 6,0 читается как «два признака выше P95». Проверки блока 4 показывают, что ранжирование по скору убирает больше оборота и связности, чем случайный выбор, в тех же единицах (узлы, KZT).

## Упоминаем в README

Масштабирование до ~1 млн узлов:

- кластеры: Leiden (igraph или leidenalg) вместо Louvain с гарантией связности сообществ; Infomap для полных данных банка, где потоки возвращаются (на нашем обходе он дробит ветки: 339 модулей против 91 у Louvain, AMI 0,66);
- betweenness: точный направленный расчёт занял 0,96 с на 2 248 узлах и растёт как произведение числа узлов и рёбер; на миллионе узлов нужна выборочная оценка по k источникам;
- временной слой: 2SCENT для перечисления временных циклов, FaSTMAN для графа переводов второго порядка, SMoTeF для отсева статических шаблонов через временной поток; FlowScope и CubeFlow для плотных цепочек с учётом суммы и времени;
- признаки на потоке: Graph Feature Preprocessor считает fan/cycle/scatter-gather на транзакциях в реальном времени; наши признаки совпадают с этим набором;
- устойчивость: collective influence (Morone, Makse) как замена перебора топ-N.

Потенциал развития, без обещаний:

- GARG-AML: один скор смёрфинга по плотности блоков окрестности второго порядка, без меток; в разведке упрощённая версия на наших данных считалась за 0,07 с, у листьев вырождается в 1 (нужна маска ≥2 соседей, с ней 157 узлов со скором ≥0,5), обрезанный второй круг у узлов глубины 4; кандидат на седьмой признак скора после сдачи обязательных пунктов;
- при появлении меток от аналитиков те же признаки идут в бустинг (Graph Feature Preprocessor) или в GNN для ориентированных мультиграфов; обзор Deprez и др. показывает, что правила и ручные признаки остаются основой большинства опубликованных систем, и предупреждает о завышенных метриках на синтетике;
- постановка триажа (Eddin и др.): ценность в сокращении очереди аналитика, метрика — доля проверок до первого подтверждения; формат вывода из конвейера Zhang и др.: одно число, объявленный порог, топ-вклады;
- калибровка правил без меток через Data Programming; независимая проверка правил через RolX (на наших данных transit при k = 6 не выделяется);
- Clue2Group и FlowSeries: постановка «от улики к группе» и банковский прецедент подхода от seed с объяснением; наш экран с поиском gid и расширением от seed совпадает с этой постановкой;
- карточка узла: счётчики взаимных пар (177), треугольников (41) и циклов длиной ≤6 (1 541, 0,05 с); число разных плательщиков за день (66 пар узел–день с ≥3 плательщиками) вместо автомата Клейнберга; достижимость с неубывающими датами (Kempe и др.) при дневной точности почти совпадает со статической и в скор не входит.

## Отвергли

- AntiBenford: порог 5 000 KZT усекает распределение первых цифр, на десятках переводов в кластере статистика неустойчива.
- LaundroGraph и структурные эмбеддинги (GraphWave, struc2vec): результат не объясняется аналитику числами и не укладывается в бюджет времени.
- HITS: со взвешиванием по сумме ненулевой hub-скор у 8 узлов и authority у 6, без весов повторяет степени; 16 слабых компонент метод игнорирует.
- pathpy: зависимость с непроверенной совместимостью ради функции, которая пишется на pandas.
- Персонализированный PageRank от seed (TRacer): все узлы по построению достижимы от seed, и оценка сводится к глубине и входящему обороту, которые уже в скоре; на полных данных банка постановка возвращается.
- Мотив «выход раньше входа» как признак приоритета и второй экспериментальный рейтинг: отклонены по итогам проверки (`hypothesis_check_2026-09-23.md`, решения 1 и 4).

## Источники

1. Li Z., Zhao Y., Hu X., Botta N., Ionescu C., Chen G. ECOD: Unsupervised Outlier Detection Using Empirical Cumulative Distribution Functions. IEEE TKDE. https://arxiv.org/abs/2201.00382
2. Climaco P. An Interpretable Approach to Money Laundering Detection in Transaction Graphs using Pass-Through Templates. arXiv, 17.09.2026. https://arxiv.org/abs/2609.20737
3. Paranjape A., Benson A., Leskovec J. Motifs in Temporal Networks. WSDM 2017. https://arxiv.org/abs/1612.09259
4. Gauvin L., Génois M., Karsai M., Kivelä M., Takaguchi T., Valdano E., Vestergaard C. Randomized reference models for temporal networks. SIAM Review 64(4), 2022. https://arxiv.org/abs/1806.04032
5. Li X., Liu S., Li Z., Han X., Shi C., Hooi B., Huang H., Cheng X. FlowScope: Spotting Money Laundering Based on Graphs. AAAI 2020. https://ojs.aaai.org/index.php/AAAI/article/view/5906
6. Altman E., Blanuša J., von Niederhäusern L., Egressy B., Anghel A., Atasu K. Realistic Synthetic Financial Transactions for Anti-Money Laundering Models. NeurIPS 2023 Datasets and Benchmarks. https://arxiv.org/abs/2306.16424
7. Morone F., Makse H. Influence maximization in complex networks through optimal percolation. Nature 524, 2015. https://arxiv.org/abs/1506.08326
8. Dugué N., Perez A. Directed Louvain: maximizing modularity in directed networks, 2015 — по документации networkx `louvain_communities`. https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.community.louvain.louvain_communities.html
9. Traag V., Waltman L., van Eck N. From Louvain to Leiden: guaranteeing well-connected communities. Scientific Reports 9, 2019. https://arxiv.org/abs/1810.08473
10. Deprez B., Baesens B., Verdonck T., Verbeke W. GARG-AML against Smurfing: A Scalable and Interpretable Graph-Based Framework for Anti-Money Laundering. arXiv 2025, v3 23.04.2026. https://arxiv.org/abs/2506.04292
11. Deprez B., Vanderschueren T., Baesens B., Verdonck T., Verbeke W. Network Analytics for Anti-Money Laundering — A Systematic Literature Review and Experimental Evaluation. arXiv 2024, ред. 2025. https://arxiv.org/abs/2405.19383
12. Eddin A., Bono J., Aparício D. и др. Anti-Money Laundering Alert Optimization Using Machine Learning with Graphs. arXiv 2021/2022. https://arxiv.org/abs/2112.07508
13. Zhang Y. и др. Detection, Attribution, Narration: An End-to-End Pipeline for Explainable Money Mule Identification. KDD 2026 Workshop on Machine Learning in Finance. https://arxiv.org/abs/2607.17586
14. Blanuša J., Cravero Baraja M., Anghel A., von Niederhäusern L., Altman E., Pozidis H., Atasu K. Graph Feature Preprocessor: Real-time Subgraph-based Feature Extraction for Financial Crime Detection. ICAIF 2024. https://arxiv.org/abs/2402.08593
15. Egressy B., von Niederhäusern L., Blanuša J., Altman E., Wattenhofer R., Atasu K. Provably Powerful Graph Neural Networks for Directed Multigraphs. AAAI 2024. https://arxiv.org/abs/2306.11586
16. Kumar R., Calders T. 2SCENT: An Efficient Algorithm for Enumerating All Simple Temporal Cycles. PVLDB 11(11), 2018. http://www.vldb.org/pvldb/vol11/p1441-kumar.pdf
17. Sun X., Zhang J., Zhao Q., Liu S., Chen J., Zhuang R., Shen H., Cheng X. CubeFlow: Money Laundering Detection with Coupled Tensors. PAKDD 2021. https://arxiv.org/pdf/2103.12411
18. Tariq H., Hassani M. Topology-Agnostic Detection of Temporal Money Laundering Flows in Billion-Scale Transactions. arXiv 2023. https://arxiv.org/abs/2309.13662
19. Capozzi A., Vilella S., Moncalvo D., Fornasiero M., Ricci V., Ronchiadin S., Ruffo G. FlowSeries: Anomaly Detection in Financial Transaction Flows. Complex Networks & Their Applications XIII, 2025. https://arxiv.org/abs/2503.15896
20. Shadrooh S., Nørvåg K. SMoTeF: Smurf money laundering detection using temporal order and flow analysis. Applied Intelligence, 2024. https://link.springer.com/article/10.1007/s10489-024-05545-4
21. Wang B., Cao J. Clue-Guided Money Laundering Group Discovery. arXiv, 24.06.2026. https://arxiv.org/abs/2606.26189
22. Smiljanić J., Blöcker C., Holmgren A., Edler D., Neuman M., Rosvall M. Community Detection with the Map Equation and Infomap: Theory and Applications. ACM Computing Surveys 58(7), 2026 (препринт 2023). https://arxiv.org/html/2311.04036v2
23. Henderson K., Gallagher B., Eliassi-Rad T., Tong H., Basu S., Akoglu L., Koutra D., Faloutsos C., Li L. RolX: Structural Role Extraction & Mining in Large Graphs. KDD 2012. https://research.google/pubs/rolx-structural-role-extraction-mining-in-large-graphs/
24. Benson A., Gleich D., Leskovec J. Higher-order organization of complex networks. Science 353(6295), 2016. https://arxiv.org/abs/1612.08447
25. Kleinberg J. Bursty and Hierarchical Structure in Streams. KDD 2002; Data Mining and Knowledge Discovery 7, 2003. https://www.cs.cornell.edu/home/kleinber/bhs.pdf
26. Kempe D., Kleinberg J., Kumar A. Connectivity and Inference Problems for Temporal Networks. STOC 2000; JCSS 64(4), 2002. https://www.sciencedirect.com/science/article/pii/S0022000002918295
27. Ratner A., De Sa C., Wu S., Selsam D., Ré C. Data Programming: Creating Large Training Sets, Quickly. NIPS 2016. https://arxiv.org/abs/1605.07723
28. Chen T., Tsourakakis C. AntiBenford Subgraphs: Unsupervised Anomaly Detection in Financial Networks. KDD 2022. https://arxiv.org/pdf/2205.13426
29. Cardoso M., Saleiro P., Bizarro P. LaundroGraph: Self-Supervised Graph Representation Learning for Anti-Money Laundering. ICAIF 2022. https://arxiv.org/abs/2210.14360
30. Kleinberg J. Authoritative Sources in a Hyperlinked Environment. JACM 1999. https://www.cs.cornell.edu/home/kleinber/auth.pdf
31. Donnat C., Zitnik M., Hallac D., Leskovec J. Learning Structural Node Embeddings via Diffusion Wavelets (GraphWave). KDD 2018. https://arxiv.org/abs/1710.10321
32. pathpy: time-respecting paths and higher-order models of temporal networks (Scholtes и др.). https://github.com/uzhdag/pathpy
33. Wu Z., Liu J., Wu J., Zheng Z. TRacer: Scalable Graph-based Transaction Tracing for Account-based Blockchain Trading Systems. arXiv 2022. https://arxiv.org/abs/2201.05757
