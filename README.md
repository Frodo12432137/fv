# Korekta prognoz pogody dla farm wiatrowych — v2

Uczenie korekt prędkości wiatru, kierunku wiatru i temperatury na podstawie
historycznych prognoz oraz pomiarów meteorologicznych na farmach. Wynik:
96 kwadransów na następne 24 godziny dla każdej skonfigurowanej farmy.

Pakiet porównuje korektę błędu farmy, korekty adaptacyjne, regresję Ridge,
kilka profili XGBoost i połączenia modeli. Chronologiczna ocena rozdziela
trening, strojenie, kalibrację i test. Kierunek jest obsługiwany na okręgu,
a cechy zawierają tylko dane dostępne przy otrzymaniu prognozy.

## Uruchomienie

**Backtest z wyborem początku i końca danych:** otwórz
[`ustawienia_backtest.example.json`](ustawienia_backtest.example.json).
Przykład uczy na okresie 2024-07-01–2026-07-01 i sprawdza prognozy na
2026-07-01–2026-08-01. W VS Code wybierz profil backtestu albo uruchom
`python start.py --settings ustawienia_backtest.example.json`.
[Instrukcja wyboru dat, strategii i odczytu błędów](JAK_ZROBIC_BACKTEST.md).

**VS Code:** otwórz folder repozytorium, przygotuj środowisko według poleceń
poniżej i wybierz je przez `Python: Select Interpreter` → `.venv`.
Zainstaluj polecane rozszerzenia Python i Python Debugger.
Następnie otwórz **`start.py` i kliknij ▶ „Uruchom plik Python”** w prawym
górnym rogu. Możesz też użyć F5 lub Ctrl+F5; gotowe profile znajdują się
w panelu „Uruchamianie i debugowanie”.

**Daty i tryb pracy ustawiasz w [`ustawienia_uruchomienia.json`](ustawienia_uruchomienia.json).**
Plik zawiera początek i koniec historii uczenia, długość walidacji i testów,
okres uruchomień prognoz oraz zakres oceny. Domyślnie wykonywany jest trening,
a po jego zatwierdzeniu jedna prognoza. `null` oznacza automatyczny dobór daty.
[Opis pól i przykład dat](URUCHAMIANIE_VSCODE.md).

Python 3.11 lub 3.12, 64-bit. Na Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-weather.txt
Copy-Item weather_config.example.json weather_config.json
```

Jeżeli zmieniasz parametry w `weather_config.json`, ustaw
`konfiguracja_modelu` na `"weather_config.json"` we wspólnym pliku ustawień.
Początkowo wskazuje on gotowy `weather_config.example.json`.

Dla SQL ustaw `PGE_WEATHER_FORECAST_CONNECTION` i
`PGE_WEATHER_OBSERVATION_CONNECTION` zgodnie z
[instrukcją konfiguracji](START_KOREKTA_POGODY_24H.md#dane-i-połączenie-sql).
Można też użyć wejść CSV bez połączenia z bazą.

Sprawdzenie ustawień bez treningu i połączenia z SQL:

```powershell
.\.venv\Scripts\python.exe start.py --check
```

Dotychczasowe polecenia terminalowe nadal działają:

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
- [Backtest jednego modelu i codziennego uczenia](JAK_ZROBIC_BACKTEST.md)
- [Przykładowy wynik backtestu kroczącego — dane syntetyczne](examples/backtest_synthetic/BACKTEST.md)
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
