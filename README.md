# Korekta prognoz pogody dla farm wiatrowych — v2

Uczenie korekt prędkości wiatru, kierunku wiatru i temperatury na podstawie
historycznych prognoz oraz pomiarów meteorologicznych na farmach. Wynik:
96 kwadransów na następne 24 godziny dla każdej skonfigurowanej farmy.

Pakiet porównuje korektę błędu farmy, korekty adaptacyjne, regresję Ridge,
kilka profili XGBoost i połączenia modeli. Chronologiczna ocena rozdziela
trening, strojenie, kalibrację i test. Kierunek jest obsługiwany na okręgu,
a cechy zawierają tylko dane dostępne przy otrzymaniu prognozy.

## Uruchomienie

Python 3.11 lub 3.12, 64-bit. Na Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-weather.txt
Copy-Item weather_config.example.json weather_config.json
```

Dla SQL ustaw `PGE_WEATHER_FORECAST_CONNECTION` i
`PGE_WEATHER_OBSERVATION_CONNECTION` zgodnie z
[instrukcją konfiguracji](START_KOREKTA_POGODY_24H.md#dane-i-połączenie-sql).
Można też użyć wejść CSV bez połączenia z bazą.

```powershell
.\.venv\Scripts\python.exe uruchom_trening_pogody.py --config weather_config.json
.\.venv\Scripts\python.exe uruchom_korekte_pogody.py
```

Uczenie można wywoływać raz dziennie, a predykcję po każdym nowym wydaniu
prognozy. Harmonogram jobów Jenkins ustawiany jest poza tym pakietem.

## Dokumentacja i sprawdzenie

- [Pełna instrukcja, format danych i założenia czasu](START_KOREKTA_POGODY_24H.md)
- [Raport testów i ograniczenia oceny](TESTY_KOREKTA_POGODY_24H.md)
- [Statystyki modelu i ocena zapisanych prognoz](STATYSTYKI_MODELU.md)
- [Przykładowy raport statystyk — dane syntetyczne](examples/statistics/synthetic_backtest/model_statistics.md)
- [Porównanie v1 i v2 na danych syntetycznych](BENCHMARK_KOREKTA_POGODY_V2.csv)

Testy:

```powershell
.\.venv\Scripts\python.exe -m pip install pytest
.\.venv\Scripts\python.exe -m pytest tests -q
```

Lokalna ocena obejmuje dane syntetyczne. Skuteczność na danych PGE i połączenia
SQL wymagają sprawdzenia w środowisku firmowym. Prognozy, pomiary, lokalne
konfiguracje połączeń i wyuczone artefakty przechowuj poza repozytorium.
