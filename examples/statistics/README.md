# Przykładowe statystyki — wyłącznie dane syntetyczne

Raport w `synthetic_backtest/` pochodzi z generatora
`weather_correction.demo.synthetic_sources(days=90, scenario="fronts")`:
dwie farmy, pomiary co 10 minut, prognozy co 15 minut z wydań co sześć godzin.
Scenariusz symuluje przesunięcie czasowe szybkich zmian pogody.

Model: v2.1, XGBoost, 50 drzew, maksymalnie 8000 wierszy do dopasowania,
walidacja 21 dni (siedem dni strojenia i 14 dni kalibracji), dwa testy po dziewięć
dni, chwila treningu `2026-04-01T00:00:00Z`. Dokładne okresy są w JSON.
Statystyki opisują wcześniejsze modele testowe, a nie dopasowanie do treningu.

- [Raport do czytania na GitHubie](synthetic_backtest/model_statistics.md)
- [Raport HTML do pobrania i otwarcia](synthetic_backtest/model_statistics.html)
- [Pełne miary według farmy i wyprzedzenia](synthetic_backtest/model_statistics.csv)
- [Miary dzienne](synthetic_backtest/daily_statistics.csv)
- [Statystyki i definicje JSON](synthetic_backtest/model_statistics.json)

Wyniki porównują korektę z **surową prognozą w tym scenariuszu**. Nie są
porównaniem z v1 i nie są wynikami na farmach PGE. Benchmark v1/v2 ma osobny
plik `BENCHMARK_KOREKTA_POGODY_V2.csv` w głównym katalogu repozytorium.
