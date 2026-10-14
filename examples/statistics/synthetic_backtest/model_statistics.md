# Statystyki oceny modelu

DANE SYNTETYCZNE — nie jest to ocena farm PGE

Chronologiczne testy poza treningiem i walidacją

Wersja: 2.1.0

Prognozy od 2026-03-14T00:00:00+00:00 do 2026-03-31T18:00:00+00:00. Wiersze prognoz: 19296.

Dodatnia poprawa oznacza mniejszy błąd korekty. Wartości — oznaczają brak danych lub niezdefiniowaną miarę.

Bramka publikacji: zaliczona.

Ocena wcześniejszych modeli testowych. Pakiet produkcyjny ponownie uczony na całej historii wymaga późniejszej oceny zapisanych prognoz.

## Wynik łączny

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | Prędkość wiatru | m/s | 19248 | 1.352 | 0.127 | 90.585 | 0.160 | -0.001 | 0.314 |
| ALL | ALL | Temperatura | °C | 19248 | 1.434 | 0.163 | 88.625 | 0.218 | 0.003 | 0.433 |
| ALL | ALL | Kierunek wiatru | ° | 19248 | 11.903 | 2.461 | 79.324 | 3.655 | 0.751 | 8.393 |

## Pokrycie, stabilność i duże błędy

| Parametr | Pokrycie % | Brak pomiaru | Cisza wiatru | Lepsze wiersze % | Lepsze dni % | P99 korekty | Max korekty | 95% CI poprawy MAE |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Prędkość wiatru | 99.751 | 48 | 0 | 99.808 | 100.000 | 0.419 | 0.701 | 1.050 … 1.375 m/s |
| Temperatura | 99.751 | 48 | 0 | 91.989 | 100.000 | 0.698 | 1.412 | 1.213 … 1.339 °C |
| Kierunek wiatru | 99.751 | 48 | 0 | 94.810 | 100.000 | 13.750 | 18.948 | 8.394 … 10.452 ° |

## Według farmy

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAL | ALL | Prędkość wiatru | m/s | 9624 | 1.301 | 0.130 | 90.002 | 0.163 | -0.004 | 0.318 |
| GAL | ALL | Temperatura | °C | 9624 | 1.353 | 0.163 | 87.952 | 0.221 | -0.025 | 0.447 |
| GAL | ALL | Kierunek wiatru | ° | 9624 | 10.523 | 1.788 | 83.007 | 2.405 | 0.959 | 4.393 |
| KAM | ALL | Prędkość wiatru | m/s | 9624 | 1.403 | 0.125 | 91.125 | 0.157 | 0.001 | 0.311 |
| KAM | ALL | Temperatura | °C | 9624 | 1.514 | 0.163 | 89.226 | 0.216 | 0.031 | 0.423 |
| KAM | ALL | Kierunek wiatru | ° | 9624 | 13.284 | 3.134 | 76.406 | 4.575 | 0.543 | 11.516 |

## Według wyprzedzenia prognozy

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | 0-3h | Prędkość wiatru | m/s | 1728 | 1.371 | 0.129 | 90.571 | 0.163 | 0.001 | 0.314 |
| ALL | 0-3h | Temperatura | °C | 1728 | 1.452 | 0.164 | 88.735 | 0.223 | -0.006 | 0.427 |
| ALL | 0-3h | Kierunek wiatru | ° | 1728 | 11.728 | 2.083 | 82.238 | 3.008 | 0.235 | 7.278 |
| ALL | 3-6h | Prędkość wiatru | m/s | 1720 | 1.374 | 0.127 | 90.773 | 0.159 | -0.003 | 0.312 |
| ALL | 3-6h | Temperatura | °C | 1720 | 1.406 | 0.163 | 88.390 | 0.212 | 0.003 | 0.422 |
| ALL | 3-6h | Kierunek wiatru | ° | 1720 | 11.727 | 2.046 | 82.557 | 3.058 | 0.672 | 7.153 |
| ALL | 6-12h | Prędkość wiatru | m/s | 3352 | 1.370 | 0.125 | 90.894 | 0.156 | 0.001 | 0.308 |
| ALL | 6-12h | Temperatura | °C | 3352 | 1.448 | 0.155 | 89.266 | 0.208 | 0.004 | 0.412 |
| ALL | 6-12h | Kierunek wiatru | ° | 3352 | 11.871 | 2.355 | 80.165 | 3.502 | 0.827 | 8.224 |
| ALL | 12-24h | Prędkość wiatru | m/s | 6416 | 1.351 | 0.125 | 90.763 | 0.156 | -0.001 | 0.305 |
| ALL | 12-24h | Temperatura | °C | 6416 | 1.422 | 0.160 | 88.732 | 0.214 | 0.002 | 0.423 |
| ALL | 12-24h | Kierunek wiatru | ° | 6416 | 11.997 | 2.433 | 79.723 | 3.481 | 1.098 | 7.563 |
| ALL | 24-36h | Prędkość wiatru | m/s | 6032 | 1.331 | 0.131 | 90.165 | 0.165 | -0.003 | 0.325 |
| ALL | 24-36h | Temperatura | °C | 6032 | 1.440 | 0.170 | 88.187 | 0.229 | 0.005 | 0.455 |
| ALL | 24-36h | Kierunek wiatru | ° | 6032 | 11.922 | 2.777 | 76.704 | 4.203 | 0.511 | 11.058 |

## Farma i wyprzedzenie

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| GAL | 0-3h | Prędkość wiatru | m/s | 864 | 1.315 | 0.128 | 90.247 | 0.162 | -0.006 | 0.314 |
| GAL | 0-3h | Temperatura | °C | 864 | 1.370 | 0.167 | 87.818 | 0.232 | -0.024 | 0.466 |
| GAL | 0-3h | Kierunek wiatru | ° | 864 | 10.392 | 1.973 | 81.016 | 2.779 | 0.477 | 6.479 |
| GAL | 3-6h | Prędkość wiatru | m/s | 860 | 1.328 | 0.133 | 89.974 | 0.166 | -0.000 | 0.319 |
| GAL | 3-6h | Temperatura | °C | 860 | 1.329 | 0.162 | 87.823 | 0.212 | -0.029 | 0.430 |
| GAL | 3-6h | Kierunek wiatru | ° | 860 | 10.315 | 1.581 | 84.675 | 2.067 | 0.866 | 3.906 |
| GAL | 6-12h | Prędkość wiatru | m/s | 1676 | 1.318 | 0.127 | 90.354 | 0.159 | -0.002 | 0.310 |
| GAL | 6-12h | Temperatura | °C | 1676 | 1.368 | 0.157 | 88.533 | 0.212 | -0.022 | 0.435 |
| GAL | 6-12h | Kierunek wiatru | ° | 1676 | 10.487 | 1.646 | 84.304 | 2.202 | 0.925 | 4.055 |
| GAL | 12-24h | Prędkość wiatru | m/s | 3208 | 1.300 | 0.127 | 90.196 | 0.159 | -0.003 | 0.309 |
| GAL | 12-24h | Temperatura | °C | 3208 | 1.343 | 0.159 | 88.143 | 0.215 | -0.026 | 0.433 |
| GAL | 12-24h | Kierunek wiatru | ° | 3208 | 10.614 | 1.730 | 83.699 | 2.276 | 1.012 | 4.084 |
| GAL | 24-36h | Prędkość wiatru | m/s | 3016 | 1.281 | 0.134 | 89.528 | 0.169 | -0.007 | 0.334 |
| GAL | 24-36h | Temperatura | °C | 3016 | 1.359 | 0.170 | 87.501 | 0.231 | -0.025 | 0.461 |
| GAL | 24-36h | Kierunek wiatru | ° | 3016 | 10.543 | 1.935 | 81.645 | 2.612 | 1.087 | 4.549 |
| KAM | 0-3h | Prędkość wiatru | m/s | 864 | 1.426 | 0.130 | 90.868 | 0.164 | 0.008 | 0.314 |
| KAM | 0-3h | Temperatura | °C | 864 | 1.534 | 0.160 | 89.553 | 0.213 | 0.012 | 0.396 |
| KAM | 0-3h | Kierunek wiatru | ° | 864 | 13.064 | 2.193 | 83.210 | 3.221 | -0.008 | 7.808 |
| KAM | 3-6h | Prędkość wiatru | m/s | 860 | 1.420 | 0.120 | 91.520 | 0.151 | -0.006 | 0.300 |
| KAM | 3-6h | Temperatura | °C | 860 | 1.484 | 0.165 | 88.897 | 0.212 | 0.035 | 0.413 |
| KAM | 3-6h | Kierunek wiatru | ° | 860 | 13.138 | 2.510 | 80.894 | 3.799 | 0.477 | 9.656 |
| KAM | 6-12h | Prędkość wiatru | m/s | 1676 | 1.421 | 0.122 | 91.394 | 0.153 | 0.003 | 0.306 |
| KAM | 6-12h | Temperatura | °C | 1676 | 1.528 | 0.154 | 89.923 | 0.203 | 0.031 | 0.405 |
| KAM | 6-12h | Kierunek wiatru | ° | 1676 | 13.256 | 3.063 | 76.890 | 4.436 | 0.728 | 11.104 |
| KAM | 12-24h | Prędkość wiatru | m/s | 3208 | 1.402 | 0.122 | 91.289 | 0.153 | 0.001 | 0.294 |
| KAM | 12-24h | Temperatura | °C | 3208 | 1.502 | 0.161 | 89.258 | 0.213 | 0.030 | 0.418 |
| KAM | 12-24h | Kierunek wiatru | ° | 3208 | 13.381 | 3.135 | 76.568 | 4.365 | 1.184 | 10.871 |
| KAM | 24-36h | Prędkość wiatru | m/s | 3016 | 1.382 | 0.128 | 90.756 | 0.162 | 0.000 | 0.320 |
| KAM | 24-36h | Temperatura | °C | 3016 | 1.521 | 0.170 | 88.799 | 0.227 | 0.035 | 0.451 |
| KAM | 24-36h | Kierunek wiatru | ° | 3016 | 13.300 | 3.620 | 72.786 | 5.339 | -0.064 | 13.275 |

## Test / zbiór: 1

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | Prędkość wiatru | m/s | 9624 | 1.393 | 0.127 | 90.903 | 0.159 | -0.016 | 0.310 |
| ALL | ALL | Temperatura | °C | 9624 | 1.423 | 0.133 | 90.661 | 0.173 | 0.012 | 0.336 |
| ALL | ALL | Kierunek wiatru | ° | 9624 | 11.874 | 2.436 | 79.485 | 3.640 | 0.545 | 8.592 |

## Test / zbiór: 2

| Farma | Horyzont | Parametr | Jednostka | N | MAE surowe | MAE korekty | Poprawa % | RMSE korekty | Bias korekty | P95 korekty |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ALL | ALL | Prędkość wiatru | m/s | 9624 | 1.311 | 0.128 | 90.247 | 0.161 | 0.014 | 0.318 |
| ALL | ALL | Temperatura | °C | 9624 | 1.445 | 0.193 | 86.620 | 0.256 | -0.007 | 0.509 |
| ALL | ALL | Kierunek wiatru | ° | 9624 | 11.933 | 2.486 | 79.164 | 3.670 | 0.957 | 8.206 |

## Dzienna ocena

| Dzień UTC | Parametr | N | MAE surowe | MAE korekty | Poprawa % |
| --- | --- | --- | --- | --- | --- |
| 2026-03-14 | Prędkość wiatru | 1152 | 1.681 | 0.118 | 92.953 |
| 2026-03-14 | Temperatura | 1152 | 1.306 | 0.134 | 89.754 |
| 2026-03-14 | Kierunek wiatru | 1152 | 12.581 | 2.205 | 82.475 |
| 2026-03-15 | Prędkość wiatru | 1152 | 1.403 | 0.125 | 91.113 |
| 2026-03-15 | Temperatura | 1152 | 1.251 | 0.118 | 90.603 |
| 2026-03-15 | Kierunek wiatru | 1152 | 15.597 | 3.311 | 78.771 |
| 2026-03-16 | Prędkość wiatru | 1152 | 0.947 | 0.133 | 85.965 |
| 2026-03-16 | Temperatura | 1152 | 1.388 | 0.099 | 92.887 |
| 2026-03-16 | Kierunek wiatru | 1152 | 10.359 | 1.956 | 81.113 |
| 2026-03-17 | Prędkość wiatru | 1152 | 1.101 | 0.123 | 88.854 |
| 2026-03-17 | Temperatura | 1152 | 1.553 | 0.092 | 94.087 |
| 2026-03-17 | Kierunek wiatru | 1152 | 9.038 | 2.972 | 67.121 |
| 2026-03-18 | Prędkość wiatru | 1152 | 1.537 | 0.124 | 91.922 |
| 2026-03-18 | Temperatura | 1152 | 1.359 | 0.127 | 90.673 |
| 2026-03-18 | Kierunek wiatru | 1152 | 13.753 | 2.348 | 82.924 |
| 2026-03-19 | Prędkość wiatru | 1152 | 1.628 | 0.123 | 92.456 |
| 2026-03-19 | Temperatura | 1152 | 1.363 | 0.159 | 88.315 |
| 2026-03-19 | Kierunek wiatru | 1152 | 13.736 | 2.812 | 79.526 |
| 2026-03-20 | Prędkość wiatru | 1152 | 1.406 | 0.128 | 90.863 |
| 2026-03-20 | Temperatura | 1152 | 1.428 | 0.158 | 88.941 |
| 2026-03-20 | Kierunek wiatru | 1152 | 10.235 | 1.892 | 81.518 |
| 2026-03-21 | Prędkość wiatru | 1096 | 1.394 | 0.132 | 90.507 |
| 2026-03-21 | Temperatura | 1096 | 1.680 | 0.150 | 91.053 |
| 2026-03-21 | Kierunek wiatru | 1096 | 9.794 | 2.289 | 76.625 |
| 2026-03-22 | Prędkość wiatru | 464 | 1.512 | 0.145 | 90.379 |
| 2026-03-22 | Temperatura | 464 | 1.583 | 0.201 | 87.299 |
| 2026-03-22 | Kierunek wiatru | 464 | 11.374 | 1.678 | 85.244 |
| 2026-03-23 | Prędkość wiatru | 1152 | 1.493 | 0.122 | 91.827 |
| 2026-03-23 | Temperatura | 1152 | 1.431 | 0.310 | 78.341 |
| 2026-03-23 | Kierunek wiatru | 1152 | 13.610 | 2.139 | 84.282 |
| 2026-03-24 | Prędkość wiatru | 1152 | 0.991 | 0.134 | 86.462 |
| 2026-03-24 | Temperatura | 1152 | 1.448 | 0.235 | 83.785 |
| 2026-03-24 | Kierunek wiatru | 1152 | 12.511 | 2.585 | 79.339 |
| 2026-03-25 | Prędkość wiatru | 1152 | 0.853 | 0.124 | 85.473 |
| 2026-03-25 | Temperatura | 1152 | 1.608 | 0.182 | 88.706 |
| 2026-03-25 | Kierunek wiatru | 1152 | 8.342 | 2.439 | 70.768 |
| 2026-03-26 | Prędkość wiatru | 1152 | 1.260 | 0.125 | 90.110 |
| 2026-03-26 | Temperatura | 1152 | 1.387 | 0.230 | 83.442 |
| 2026-03-26 | Kierunek wiatru | 1152 | 10.556 | 2.076 | 80.333 |
| 2026-03-27 | Prędkość wiatru | 1152 | 1.310 | 0.120 | 90.808 |
| 2026-03-27 | Temperatura | 1152 | 1.387 | 0.243 | 82.465 |
| 2026-03-27 | Kierunek wiatru | 1152 | 16.053 | 3.543 | 77.929 |
| 2026-03-28 | Prędkość wiatru | 1152 | 1.049 | 0.131 | 87.489 |
| 2026-03-28 | Temperatura | 1152 | 1.424 | 0.159 | 88.824 |
| 2026-03-28 | Kierunek wiatru | 1152 | 11.720 | 2.581 | 77.981 |
| 2026-03-29 | Prędkość wiatru | 1152 | 1.403 | 0.130 | 90.759 |
| 2026-03-29 | Temperatura | 1152 | 1.561 | 0.110 | 92.975 |
| 2026-03-29 | Kierunek wiatru | 1152 | 8.231 | 2.094 | 74.556 |
| 2026-03-30 | Prędkość wiatru | 1096 | 1.888 | 0.128 | 93.219 |
| 2026-03-30 | Temperatura | 1096 | 1.368 | 0.110 | 91.996 |
| 2026-03-30 | Kierunek wiatru | 1096 | 12.767 | 2.260 | 82.294 |
| 2026-03-31 | Prędkość wiatru | 464 | 1.974 | 0.149 | 92.428 |
| 2026-03-31 | Temperatura | 464 | 1.297 | 0.106 | 91.794 |
| 2026-03-31 | Kierunek wiatru | 464 | 16.184 | 2.890 | 82.143 |

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
