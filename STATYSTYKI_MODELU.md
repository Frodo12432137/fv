# Statystyki oceny modelu

Do wyuczenia modelu na jednym okresie i sprawdzenia go na późniejszych danych
użyj [backtestu z czterema datami](JAK_ZROBIC_BACKTEST.md). Test kroczący
odtwarza także codzienne uczenie i zachowuje wersję modelu każdego uruchomienia.

Każdy trening zapisuje raport oceny w katalogu `weather_artifacts/model-.../`:

- `model_statistics.html` — raport do otwarcia w przeglądarce;
- `model_statistics.md` — te same tabele w Markdown;
- `model_statistics.json` — pełne statystyki, opis danych i definicje;
- `model_statistics.csv` — statystyki według testu, farmy i wyprzedzenia;
- `daily_statistics.csv` — dzienna ocena wszystkich farm.

Raport dotyczy chronologicznych testów poza treningiem i walidacją.
Modele produkcyjne są później ponownie uczone na pełnej historii; ich przyszłą
skuteczność oceniamy dopiero po nadejściu pomiarów. Raport powstaje również dla
kandydata odrzuconego przez bramkę publikacji.

## Jak czytać liczby

| Statystyka | Znaczenie |
|---|---|
| MAE | Średni błąd absolutny; mniejszy jest lepszy. |
| RMSE | Silniej uwzględnia duże błędy; mniejszy jest lepszy. |
| Bias | Prognoza minus pomiar. Dodatni oznacza zawyżanie. Dla kierunku to podpisany błąd kątowy. |
| Mediana / P90 / P95 / P99 | Połowa / 90% / 95% / 99% błędów absolutnych nie przekracza tej wartości. |
| Maksymalny błąd | Największy błąd absolutny w ocenianych prognozach. |
| R² | Porównanie błędu ze zmiennością pomiarów. Może być ujemne; brak przy stałych pomiarach i dla kierunku. |
| Poprawa MAE / RMSE % | `100 × (1 − błąd korekty / błąd surowej prognozy)`. Dodatnia = poprawa, ujemna = pogorszenie. Przy zerowym błędzie surowym brak wartości. |
| Lepsze / gorsze / remisowe wiersze % | Jak często korekta miała mniejszy / większy / równy błąd. |
| Lepsze dni % | Jak często dzienne MAE korekty było mniejsze. |
| Pokrycie % | Odsetek prognoz, które można ocenić na dostępnych, poprawnych pomiarach. |
| N | Liczba ocenionych prognoz dla danego parametru, farmy i horyzontu. |
| 95% CI poprawy MAE | Przedział oszacowania różnicy `MAE surowe − MAE korekty`. Cały dodatni przedział sugeruje stabilną poprawę. |

Prędkość i jej błędy są w m/s, temperatura i jej błędy w °C, kierunek i jego
błędy w stopniach. Kierunek liczymy po najkrótszej drodze na okręgu:
359° względem 1° daje błąd 2°. Nie oceniamy kierunku przy prędkości pomiaru
poniżej `calm_speed` ani wtedy, gdy prędkość pomiaru jest nieznana.

Pełny CSV zawiera też odsetek błędów nieprzekraczających 1 m/s, 1°C i 15°.
To progi opisowe; nie są zatwierdzonymi kryteriami biznesowymi.

Wyniki dzielimy na wszystkie farmy łącznie, każdą farmę, wyprzedzenia 0–3,
3–6, 6–12, 12–24 i 24–36 godzin oraz połączenia farmy i wyprzedzenia.
Wyprzedzenie liczymy od dostępności paczki. Zakres 24–36 godzin pozwala
ocenić prognozę, która przy uruchomieniu ma już kilka godzin.

Wynik `fold=pooled` obliczamy bezpośrednio z błędów wszystkich testów.
Nie uśredniamy percentyli, RMSE ani R² poszczególnych testów. Prognozę surową
i skorygowaną porównujemy zawsze na identycznych poprawnych pomiarach.
W liczniku pokrycia pozostają także kwadranse całkowicie pozbawione wykonania.
Oceniane są tylko kwadranse kończące się do końca danego testu; pomiary muszą
być dostępne do tego odcięcia czasu.

Jedna obserwacja może weryfikować kilka wydań prognozy. Dlatego liczba wierszy
nie oznacza liczby niezależnych pomiarów. Przedział poprawy MAE używa 500
losowań dwudniowych bloków dni UTC wydania/predykcji i wymaga co najmniej
siedmiu ocenionych dni. Jest diagnostyczny, bez korekty na wiele porównań.
Nie jest przedziałem niepewności przyszłego wiatru lub temperatury.

## Rodzaj danych

Przy treningu można podać `--data-kind measured`, `synthetic` albo `unspecified`.
Ta flaga opisuje pochodzenie danych w raporcie, nie zmienia modelu.
Domyślnie raport informuje, że rodzaju danych nie określono. Przykład:

```powershell
.\.venv\Scripts\python.exe uruchom_trening_pogody.py --config weather_config.json --data-kind measured
```

[Przykładowy raport w repozytorium](examples/statistics/synthetic_backtest/model_statistics.md)
pochodzi wyłącznie z danych syntetycznych. Nie przedstawia skuteczności na PGE.

## Ocena zapisanych prognoz po nadejściu wykonania

Zachowuj kopie CSV predykcji z kolejnych uruchomień. Domyślny plik wyniku
jest nadpisywany, więc przy archiwizowaniu użyj `--output` z osobną nazwą.
Nie odtwarzaj starej prognozy modelem wyuczonym na późniejszych pomiarach.

Po nadejściu pomiarów uruchom:

```powershell
.\.venv\Scripts\python.exe ocen_prognoze_pogody.py --config weather_config.json --predictions-csv prognoza_1.csv prognoza_2.csv --observation-csv pomiary.csv --data-kind measured --output weather_output\evaluation
```

`--config` musi odpowiadać konfiguracji treningu zapisanej prognozy, w tym
znaczeniu i opóźnieniu pomiarów. `pomiary.csv` ma taki sam format, jak wejście
pomiarów do treningu. Możesz podać `--as-of` z offsetem, aby ocenić tylko
pomiary dostępne do konkretnej chwili. `--csv-separator ";"` ustawia separator
pomiarów; oryginalne pliki predykcji programu są zawsze czytane z przecinkiem.
Dla predykcji przekonwertowanych do innego separatora podaj osobno
`--predictions-separator ";"`.

Skrypt dołącza rzeczywiste pomiary po farmie i kwadransie w UTC. Identyczne
kopie tych samych prognoz usuwa z liczników. Sprzeczne kopie albo różne
`modelVersion` w jednym zestawie są błędem: wersje należy oceniać osobno.
Pomiary przyszłe lub dostarczone po `as-of` nie wchodzą do oceny.
Filtr `--start`/`--end` jest stosowany przed sprawdzaniem wersji i czasu
predykcji, więc inny model albo późniejsza prognoza poza wybranym okresem
nie blokują oceny tego okresu. W samym wybranym okresie nadal oceniaj jedną
wersję naraz; backtest kroczący łączy własne kolejne wersje jako wynik jednej
procedury uczenia i daje też osobne statystyki dla każdej wersji.

Kod zakończenia: `0` raport z ocenionymi pomiarami, `1` błąd danych lub
konfiguracji, `2` raport powstał, ale nie ma jeszcze żadnych poprawnych
pomiarów do oceny. Dostępność części pomiarów pokazuje pokrycie; kod `0`
sam w sobie nie oznacza pełnego pokrycia lub dobrych wyników modelu.
