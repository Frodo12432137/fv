# Statystyki oceny modelu

DANE SYNTETYCZNE — nie jest to ocena farm PGE

Backtest historyczny: kroczacy

Wersja: Kolejne wersje tej samej procedury uczenia

Prognozy od 2026-02-02T00:00:00+00:00 do 2026-02-09T18:00:00+00:00. Wiersze prognoz: 2924.

Dodatnia poprawa oznacza mniejszy błąd korekty. Wartości — oznaczają brak danych lub niezdefiniowaną miarę.

Ocena obejmuje wyłącznie prognozowane kwadranse w wybranym okresie backtestu. Modele nie znają przyszłych pomiarów; późniejsze wykonanie służy wyłącznie ocenie. Błędy liczymy dla udanych prognoz, a brakujące uruchomienia osobno w prediction_runs.csv. Ponowne uczenie jest symulowane w chwili odcięcia danych, bez modelowania czasu obliczeń.

Dane pierwszego uczenia: 2026-01-01T00:00:00+00:00 – 2026-02-02T00:00:00+00:00. Okres backtestu: 2026-02-02T00:00:00+00:00 – 2026-02-10T00:00:00+00:00 (koniec wyłączny). Strategia: kroczacy; krok uruchomień: 6 h.

Pokrycie generowania prognoz: 100.000%. Nieudane uruchomienia: 0. Pokrycie pomiarów w tabelach dotyczy wygenerowanych prognoz.

## Wynik łączny

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | Prędkość wiatru | m/s | 2924 | 1.257 | 0.030 | 97.633 | 0.038 | 0.007 | 0.075 |
| ALL | ALL | Temperatura | °C | 2924 | 1.201 | 0.019 | 98.383 | 0.024 | 0.001 | 0.047 |
| ALL | ALL | Kierunek wiatru | ° | 2924 | 12.001 | 0.184 | 98.467 | 0.232 | -0.003 | 0.451 |

## Pokrycie, stabilność i duże błędy

| Parametr | Pokrycie % | Brak pomiaru | Cisza wiatru | Lepsze wiersze % | Lepsze dni % | P99 korekty | Max korekty | 95% CI poprawy MAE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Prędkość wiatru | 100.000 | 0 | 0 | 100.000 | 100.000 | 0.098 | 0.123 | 1.084 … 1.384 m/s |
| Temperatura | 100.000 | 0 | 0 | 100.000 | 100.000 | 0.060 | 0.075 | 1.180 … 1.183 °C |
| Kierunek wiatru | 100.000 | 0 | 0 | 100.000 | 100.000 | 0.624 | 0.852 | 11.795 … 11.842 ° |

## Według farmy

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAL | ALL | Prędkość wiatru | m/s | 2924 | 1.257 | 0.030 | 97.633 | 0.038 | 0.007 | 0.075 |
| GAL | ALL | Temperatura | °C | 2924 | 1.201 | 0.019 | 98.383 | 0.024 | 0.001 | 0.047 |
| GAL | ALL | Kierunek wiatru | ° | 2924 | 12.001 | 0.184 | 98.467 | 0.232 | -0.003 | 0.451 |

## Według wyprzedzenia prognozy

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | 0-3h | Prędkość wiatru | m/s | 384 | 1.243 | 0.032 | 97.400 | 0.041 | 0.003 | 0.082 |
| ALL | 0-3h | Temperatura | °C | 384 | 1.201 | 0.019 | 98.459 | 0.023 | 0.001 | 0.046 |
| ALL | 0-3h | Kierunek wiatru | ° | 384 | 12.002 | 0.182 | 98.484 | 0.231 | -0.000 | 0.485 |
| ALL | 3-6h | Prędkość wiatru | m/s | 383 | 1.244 | 0.027 | 97.812 | 0.034 | 0.002 | 0.069 |
| ALL | 3-6h | Temperatura | °C | 383 | 1.201 | 0.020 | 98.330 | 0.025 | 0.001 | 0.048 |
| ALL | 3-6h | Kierunek wiatru | ° | 383 | 11.999 | 0.185 | 98.457 | 0.231 | -0.004 | 0.439 |
| ALL | 6-12h | Prędkość wiatru | m/s | 743 | 1.253 | 0.029 | 97.665 | 0.037 | 0.006 | 0.075 |
| ALL | 6-12h | Temperatura | °C | 743 | 1.201 | 0.019 | 98.400 | 0.024 | 0.000 | 0.047 |
| ALL | 6-12h | Kierunek wiatru | ° | 743 | 12.001 | 0.182 | 98.480 | 0.230 | -0.006 | 0.446 |
| ALL | 12-24h | Prędkość wiatru | m/s | 1414 | 1.267 | 0.030 | 97.631 | 0.038 | 0.011 | 0.075 |
| ALL | 12-24h | Temperatura | °C | 1414 | 1.201 | 0.020 | 98.368 | 0.024 | 0.001 | 0.048 |
| ALL | 12-24h | Kierunek wiatru | ° | 1414 | 12.002 | 0.185 | 98.458 | 0.233 | -0.003 | 0.452 |

## Farma i wyprzedzenie

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAL | 0-3h | Prędkość wiatru | m/s | 384 | 1.243 | 0.032 | 97.400 | 0.041 | 0.003 | 0.082 |
| GAL | 0-3h | Temperatura | °C | 384 | 1.201 | 0.019 | 98.459 | 0.023 | 0.001 | 0.046 |
| GAL | 0-3h | Kierunek wiatru | ° | 384 | 12.002 | 0.182 | 98.484 | 0.231 | -0.000 | 0.485 |
| GAL | 3-6h | Prędkość wiatru | m/s | 383 | 1.244 | 0.027 | 97.812 | 0.034 | 0.002 | 0.069 |
| GAL | 3-6h | Temperatura | °C | 383 | 1.201 | 0.020 | 98.330 | 0.025 | 0.001 | 0.048 |
| GAL | 3-6h | Kierunek wiatru | ° | 383 | 11.999 | 0.185 | 98.457 | 0.231 | -0.004 | 0.439 |
| GAL | 6-12h | Prędkość wiatru | m/s | 743 | 1.253 | 0.029 | 97.665 | 0.037 | 0.006 | 0.075 |
| GAL | 6-12h | Temperatura | °C | 743 | 1.201 | 0.019 | 98.400 | 0.024 | 0.000 | 0.047 |
| GAL | 6-12h | Kierunek wiatru | ° | 743 | 12.001 | 0.182 | 98.480 | 0.230 | -0.006 | 0.446 |
| GAL | 12-24h | Prędkość wiatru | m/s | 1414 | 1.267 | 0.030 | 97.631 | 0.038 | 0.011 | 0.075 |
| GAL | 12-24h | Temperatura | °C | 1414 | 1.201 | 0.020 | 98.368 | 0.024 | 0.001 | 0.048 |
| GAL | 12-24h | Kierunek wiatru | ° | 1414 | 12.002 | 0.185 | 98.458 | 0.233 | -0.003 | 0.452 |

## Test / zbiór: backtest

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | Prędkość wiatru | m/s | 2924 | 1.257 | 0.030 | 97.633 | 0.038 | 0.007 | 0.075 |
| ALL | ALL | Temperatura | °C | 2924 | 1.201 | 0.019 | 98.383 | 0.024 | 0.001 | 0.047 |
| ALL | ALL | Kierunek wiatru | ° | 2924 | 12.001 | 0.184 | 98.467 | 0.232 | -0.003 | 0.451 |

## Dzienna ocena

| Dzień UTC | Parametr | N | MAE surowe | MAE korekty | Poprawa % |
| --- | --- | --- | --- | --- | --- |
| 2026-02-02 | Prędkość wiatru | 384 | 1.003 | 0.031 | 96.898 |
| 2026-02-02 | Temperatura | 384 | 1.201 | 0.018 | 98.462 |
| 2026-02-02 | Kierunek wiatru | 384 | 12.011 | 0.167 | 98.610 |
| 2026-02-03 | Prędkość wiatru | 384 | 1.061 | 0.027 | 97.408 |
| 2026-02-03 | Temperatura | 384 | 1.206 | 0.021 | 98.267 |
| 2026-02-03 | Kierunek wiatru | 384 | 12.046 | 0.186 | 98.454 |
| 2026-02-04 | Prędkość wiatru | 384 | 1.158 | 0.030 | 97.410 |
| 2026-02-04 | Temperatura | 384 | 1.197 | 0.021 | 98.265 |
| 2026-02-04 | Kierunek wiatru | 384 | 12.013 | 0.181 | 98.490 |
| 2026-02-05 | Prędkość wiatru | 384 | 1.301 | 0.036 | 97.246 |
| 2026-02-05 | Temperatura | 384 | 1.204 | 0.020 | 98.366 |
| 2026-02-05 | Kierunek wiatru | 384 | 12.002 | 0.186 | 98.452 |
| 2026-02-06 | Prędkość wiatru | 384 | 1.361 | 0.031 | 97.701 |
| 2026-02-06 | Temperatura | 384 | 1.200 | 0.017 | 98.565 |
| 2026-02-06 | Kierunek wiatru | 384 | 11.980 | 0.176 | 98.533 |
| 2026-02-07 | Prędkość wiatru | 384 | 1.449 | 0.027 | 98.105 |
| 2026-02-07 | Temperatura | 384 | 1.201 | 0.019 | 98.392 |
| 2026-02-07 | Kierunek wiatru | 384 | 11.994 | 0.196 | 98.366 |
| 2026-02-08 | Prędkość wiatru | 384 | 1.428 | 0.026 | 98.177 |
| 2026-02-08 | Temperatura | 384 | 1.199 | 0.020 | 98.347 |
| 2026-02-08 | Kierunek wiatru | 384 | 11.987 | 0.191 | 98.408 |
| 2026-02-09 | Prędkość wiatru | 236 | 1.323 | 0.028 | 97.864 |
| 2026-02-09 | Temperatura | 236 | 1.199 | 0.019 | 98.415 |
| 2026-02-09 | Kierunek wiatru | 236 | 11.962 | 0.193 | 98.390 |

## Interpretacja

Te same poprawne etykiety dla prognozy surowej i skorygowanej.

Najkrótszy błąd na okręgu, od -180 do 180°. Pomijamy wiatr poniżej 1.0 m/s.

Prognoza minus pomiar; dodatni bias oznacza zawyżanie (dla kierunku przesunięcie kątowe).

95% przedział z 500 losowań dwudniowych bloków dni UTC wydania/predykcji; minimum 7 dni. Diagnostyczny, bez korekty na wiele porównań.

Wiersz oznacza jedną ocenioną prognozę. Różne paczki mogą dotyczyć tego samego pomiaru; wiersze nie są niezależnymi pomiarami.

Statystyki łączne liczymy z błędów wszystkich testów, bez uśredniania percentyli lub R².

Tylko prędkość i temperatura; brak przy stałych pomiarach. Dla kierunku nie stosujemy zwykłego R².

Progi opisowe: 1 m/s, 1°C, 15°. Nie stanowią zatwierdzonych kryteriów biznesowych.

Pełne statystyki (w tym R², mediany, percentyle i błędy surowe) są w model_statistics.csv i model_statistics.json.
