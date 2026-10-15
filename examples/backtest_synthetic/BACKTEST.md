# Przykład backtestu — DANE SYNTETYCZNE

**Wymyślone dane sprawdzają działanie programu. To nie jest ocena farm PGE.**

Strategia: **kroczacy**. Rodzaj danych: **synthetic**.

Uczenie pierwszego modelu: 2026-01-01T00:00:00+00:00 – 2026-02-02T00:00:00+00:00.

Backtest: 2026-02-02T00:00:00+00:00 – 2026-02-10T00:00:00+00:00 (koniec wyłączny).

Udane uruchomienia: 32/32. Pokrycie generowania prognoz: 100.00%.

[Statystyki błędu](model_statistics.md) · [HTML](model_statistics.html) · [Historia uczenia](training_runs.csv) · [Historia prognoz](prediction_runs.csv)

Porównuj MAE/RMSE korekty z prognozą surową, sprawdzając również P95, bias, pokrycie pomiarów i liczbę dni. Wynik tego backtestu nie służy do wyboru parametrów na tym samym okresie; kolejne zmiany wymagają kolejnego niezależnego okresu.

| Parametr | Jednostka | N | MAE surowe | MAE modelu | Poprawa % | RMSE modelu | P95 modelu |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Prędkość wiatru | m/s | 2924 | 1.257 | 0.030 | 97.633 | 0.038 | 0.075 |
| Temperatura | °C | 2924 | 1.201 | 0.019 | 98.383 | 0.024 | 0.047 |
| Kierunek wiatru | ° | 2924 | 12.001 | 0.184 | 98.467 | 0.232 | 0.451 |
