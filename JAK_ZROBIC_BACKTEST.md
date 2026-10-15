# Start i stop danych oraz rzeczywisty backtest

Ustawiasz **cztery daty**: początek i koniec uczenia oraz początek i koniec
backtestu. Model uczy się na wcześniejszych danych. Następnie program odtwarza
późniejsze prognozy i porównuje je z rzeczywistymi pomiarami farm.

## Najprostszy przykład: uczenie od lipca 2024 do lipca 2026

Gotowy plik `ustawienia_backtest.example.json` zawiera:

| Dane | Początek włącznie | Koniec wyłącznie |
|---|---|---|
| Uczenie pierwszego modelu | 1 lipca 2024 | 1 lipca 2026 |
| Niezależny backtest | 1 lipca 2026 | 1 sierpnia 2026 |

Daty mają godzinę i offset Polski. W pliku ustawień najważniejsze są te pola:

```json
{
  "tryb": "backtest",
  "trening": {
    "start": "2024-07-01T00:00:00+02:00",
    "koniec": "2026-07-01T00:00:00+02:00",
    "dni_walidacji": 21,
    "dni_testu": 21,
    "liczba_testow": 2
  },
  "backtest": {
    "start": "2026-07-01T00:00:00+02:00",
    "koniec": "2026-08-01T00:00:00+02:00",
    "strategia": "staly",
    "krok_godziny": 6,
    "odswiezaj_model_co_dni": 1,
    "pomiary_dostepne_do": null,
    "katalog_wynikow": "weather_output/backtest"
  }
}
```

To fragment istniejącego pliku, nie jego cała zawartość. Ustaw też połączenia
SQL zgodnie z główną instrukcją albo ścieżki do obu CSV w sekcji `dane`.
Pliki wejściowe muszą zawierać historię i cały okres backtestu. `konfiguracja_modelu`
wskazuje konfigurację farm, pomiarów, opóźnień i samych modeli.

Najpierw sprawdź plan bez pobierania danych:

```powershell
.\.venv\Scripts\python.exe start.py --settings ustawienia_backtest.example.json --check
```

Następnie uruchom:

```powershell
.\.venv\Scripts\python.exe start.py --settings ustawienia_backtest.example.json
```

W VS Code wybierz profil **„Pogoda: backtest historyczny (daty w przykładzie)”**
i naciśnij F5 albo Ctrl+F5. Jeżeli wolisz zwykłą strzałkę ▶ w `start.py`, skopiuj
zawartość przykładu do `ustawienia_uruchomienia.json`; ten plik jest ustawieniem
domyślnym. Zmieniaj daty w JSON, bez edycji Pythona.

Lipiec 2026 w przykładzie to 124 uruchomienia co sześć godzin. Każde generuje
96 następnych kwadransów na farmę. Do błędów backtestu wchodzą tylko kwadranse
z wybranego okresu, więc ostatnie prognozy mogą być oceniane w części ich horyzontu.

## Dwie strategie

**`staly`** — jeden model wyuczony na `trening.start`–`trening.koniec`.
Jego parametry pozostają zamrożone przez backtest. Przy kolejnych prognozach
może korzystać z pomiarów, które stały się już wtedy dostępne, tak jak w pracy
operacyjnej. To odpowiedź na pytanie: „jaki błąd miałby ten konkretny model
na późniejszym miesiącu?”.

**`kroczacy`** — pierwsze uczenie kończy się dokładnie na `backtest.start`.
Potem uczenie jest odświeżane co `odswiezaj_model_co_dni`, domyślnie co 24 godziny,
przy pierwszej potrzebnej prognozie. Historia rozszerza się od tego samego
`trening.start`, ale jej koniec przesuwa się tylko do bieżącej chwili.
Przy kroku sześć godzin odtwarzamy codzienne uczenie i cztery prognozy dziennie.
Nie czekamy na upływ prawdziwego czasu; historyczne uruchomienia liczymy kolejno.
Odstępy są liczone w rzeczywistych godzinach UTC, także przy zmianie czasu.

W przykładzie wystarczy zmienić `strategia` na `kroczacy`, aby sprawdzić
codzienne odświeżanie przez lipiec. To znacznie więcej obliczeń niż jeden model.

Jeśli chcesz sprawdzić procedurę **w środku historii 2024–2026**, możesz ustawić:
uczenie 2024-07-01–2025-01-01 i backtest kroczący 2025-01-01–2026-07-01.
Pierwsze miesiące dostarczają historii pierwszego modelu. Nie przypisujemy
modelowi prognoz z chwili, gdy nie miał jeszcze danych do nauki. Minimalna
historia zależy od konfiguracji; przy domyślnych ustawieniach potrzeba co
najmniej 123 dni na uczenie, walidację i testy wewnętrzne, a dane muszą je pokrywać.

## Jak chronimy sprawdzian przed wiedzą o przyszłości

- Trening używa tylko prognoz i pomiarów dostępnych do jego historycznego końca.
- Cechy każdej prognozy używają tylko informacji znanych przy otrzymaniu jej paczki.
- Późniejsze pomiary służą do porównania wyniku. Nie trafiają wcześniej do modelu.
- Strojenie, kalibracja i historyczna bramka publikacji są wewnątrz wcześniejszej
  historii uczenia. Nie wybierają parametrów na podstawie przyszłego sprawdzianu.
- Odrzucone ponowne uczenie pozostawia poprzedni zaakceptowany model. Jeżeli
  pierwszy model nie przejdzie bramki, backtest zatrzymuje się z kodem `2`;
  raport przyczyn i testów tego modelu znajdziesz w jego katalogu `models/`.

Backtest ma własny katalog modeli wewnątrz wyniku. Nie podmienia aktywnego
modelu używanego przez normalną predykcję. Czas liczenia treningu nie jest
symulowany jako dodatkowe opóźnienie operacyjne.

Rzetelny backtest wymaga archiwum historycznych wydań prognoz i ich rzeczywistych
czasów dostępności. Tak samo ważne są dostępność i wersje pomiarów. Jeżeli baza
przechowuje wyłącznie najnowsze poprawione dane albo czas dostarczenia jest
założeniem, symulacja ma to ograniczenie. Potwierdź znaczenie znaczników czasu
i opóźnienia z głównej konfiguracji.

## Gdzie zobaczysz rzeczywisty błąd

Każde wykonanie tworzy osobny katalog `weather_output/backtest/run-.../`:

- **`BACKTEST.md`** — zakresy dat i tabela błędów surowej prognozy oraz modelu;
- **`model_statistics.html`** — raport do przeglądarki, także według farmy,
  wyprzedzenia i dnia; wersje Markdown, CSV i JSON są obok;
- `backtest_predictions.csv` — prognozy, korekty i pomiary punkt po punkcie;
- `prediction_runs.csv` — każde historyczne uruchomienie, wersja modelu,
  jego odcięcie danych i ewentualny błąd generowania;
- `training_runs.csv` — każde uczenie i wynik historycznej bramki jakości;
- `model_versions_statistics.csv` — błędy poszczególnych użytych wersji;
- `models/` — modele i wewnętrzne raporty ich uczenia;
- `predictions/` — oryginalne CSV prognoz z poszczególnych uruchomień.

**MAE** to przeciętny błąd: m/s dla prędkości, °C dla temperatury i stopnie
po najkrótszej drodze na okręgu dla kierunku. **RMSE** mocniej uwzględnia duże
błędy, **P95** opisuje ogon rozkładu, a **bias** pokazuje stałe zawyżanie lub
zaniżanie. Poprawa procentowa jest dodatnia, gdy korekta ma mniejszy błąd.

Wybieraj rozwiązanie na podstawie poprawy wobec surowej prognozy, również
w podziale na farmy i horyzonty. Sprawdzaj, czy poprawa utrzymuje się przez dni,
czy nie rosną duże błędy i czy pokrycie danych jest wystarczające. Raport
podaje diagnostyczny przedział poprawy MAE po co najmniej siedmiu dniach.
Sam wynik R² nie wystarcza do wyboru modelu.

Porównując dwa warianty, zachowaj te same farmy, wydania pogody, chwile
uruchomień i okres oceny. Statystyki różnych dziennych wersji nie są prostym
rankingiem modeli, bo każda wersja mogła trafić na inną pogodę. Do porównania
strategii służą osobne backtesty na tym samym okresie i tych samych danych.

Pokrycie wygenerowanych prognoz i pokrycie pomiarów to dwie osobne liczby.
Brakujące lub niepełne wydania prognozy są zapisywane jako nieudane uruchomienia.
Błędy dotyczą dostępnych udanych prognoz, więc oceniaj je razem z liczbą braków.
Brak wykonania nie jest zastępowany zerem. Kierunku nie oceniamy przy ciszy
wiatru ani nieznanej zmierzonej prędkości.

Po obejrzeniu wyników możesz zmienić model, ale ten sam obejrzany okres staje
się wtedy częścią eksperymentów. Końcową ocenę takiego wyboru zrób na kolejnym
okresie, którego wyników jeszcze nie używałeś do poprawek.

Kod `0`: backtest wykonany z prognozami i pomiarami do oceny. Kod `2`: wynik
niepełny, brak udanych prognoz/pomiarów albo brak zaakceptowanego pierwszego
modelu. Kod `1`: błąd konfiguracji lub danych. Kod `0` nie oznacza automatycznie
dobrego modelu ani pełnego pokrycia pomiarów — sprawdź raport.

Tutaj zweryfikowano przepływ na danych syntetycznych. Błąd na farmach PGE
powstanie dopiero po wykonaniu backtestu na Waszym archiwum.
