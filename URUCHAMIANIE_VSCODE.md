# Start strzałką w VS Code i ustawianie dat

1. Otwórz w VS Code **folder `fv`**, nie sam pojedynczy plik.
2. Zainstaluj polecane rozszerzenia **Python** i **Python Debugger**.
3. Jednorazowo przygotuj Pythona 3.11 lub 3.12 (64-bit):

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements-weather.txt
   ```

   Na Linux/macOS: `python3 -m venv .venv`, następnie
   `.venv/bin/python -m pip install -r requirements-weather.txt`.

4. Ctrl+Shift+P → **Python: Select Interpreter** → wybierz `.venv`.
5. Ustaw daty i źródło danych w **`ustawienia_uruchomienia.json`**.
6. Otwórz **`start.py`** i kliknij **▶ Uruchom plik Python** w prawym górnym rogu.
   Wyniki i komunikaty zobaczysz w terminalu VS Code.

F5 uruchamia debugger, Ctrl+F5 startuje bez debugowania. Panel „Uruchamianie
i debugowanie” ma też profile samego treningu, samych prognoz i oceny.
Profile nadpisują wyłącznie `tryb`, pozostałe ustawienia pochodzą z tego samego pliku.

## Jedno miejsce na daty

W `ustawienia_uruchomienia.json` ustaw:

| Pole | Znaczenie | Gdy ustawisz `null` |
| --- | --- | --- |
| `trening.start` | Najwcześniejsza dostępność wydania prognozy w historii uczenia | `history_days` przed końcem uczenia (domyślnie 365 dni) |
| `trening.koniec` | Koniec historii i chwila dostępności danych dla uczenia | Chwila uruchomienia |
| `trening.dni_walidacji` | Liczba dni walidacji; nadpisuje konfigurację modelu | Wymagana liczba, domyślnie 21 |
| `trening.dni_testu` | Liczba dni pojedynczego testu chronologicznego | Wymagana liczba, domyślnie 21 |
| `trening.liczba_testow` | Liczba kolejnych testów | Wymagana liczba, domyślnie 2 |
| `prognoza.start` | Pierwsza chwila uruchomienia predykcji | Koniec uczenia w trybie łączonym; teraz w trybie samej prognozy |
| `prognoza.koniec` | Koniec okresu uruchomień predykcji | Jedna predykcja |
| `prognoza.krok_godziny` | Odstęp pomiędzy uruchomieniami, np. 6 godzin | Wymagana dodatnia liczba całkowita |
| `ocena.start` | Pierwszy oceniany kwadrans według `dataGodzinaUTC` | Bez ograniczenia początku |
| `ocena.koniec` | Koniec ocenianych kwadransów | Bez ograniczenia końca |
| `ocena.pomiary_dostepne_do` | Do tej chwili pomiary muszą być już dostępne | Chwila uruchomienia |

Wszystkie zakresy mają **początek włącznie i koniec wyłącznie**.
Zapisuj daty najlepiej z godziną i offsetem, np. `"2026-01-01T06:00:00+01:00"`.
Data bez godziny oznacza północ, a bez offsetu jest interpretowana w
`strefa_czasowa` (domyślnie `Europe/Warsaw`). Niejednoznaczne godziny zmiany czasu
wymagają offsetu. Kolejne uruchomienia są odliczane w godzinach rzeczywistych w UTC.

Przykład — zmień odpowiednie sekcje istniejącego pliku:

```json
{
  "trening": {
    "start": "2025-01-01T00:00:00+01:00",
    "koniec": "2026-01-01T00:00:00+01:00",
    "dni_walidacji": 21,
    "dni_testu": 21,
    "liczba_testow": 2
  },
  "prognoza": {
    "start": "2026-01-01T00:00:00+01:00",
    "koniec": "2026-01-02T00:00:00+01:00",
    "krok_godziny": 6,
    "katalog_wynikow": "weather_output/prognozy"
  }
}
```

To wykona trening, a następnie cztery predykcje: o 00:00, 06:00, 12:00 i 18:00.
**Każda predykcja obejmuje następne 24 godziny**, czyli 96 kwadransów na farmę.
Daty w sekcji `prognoza` określają chwile uruchomień, więc ostatni plik może
zawierać kwadranse późniejsze niż `prognoza.koniec`. Każda chwila dostaje osobny
plik z czasem UTC w nazwie. Ponowny start dla tej samej chwili zastępuje jej plik.
Pętla liczy wyniki od razu; nie czeka do godzin przyszłych uruchomień.

Historia uczenia obejmuje trening, walidację i niezależne testy.
Walidacja i test są wyznaczane chronologicznie wstecz od `trening.koniec`;
strojenie i kalibracja dzielą okres walidacji. Daty podziałów znajdziesz w
`weather_artifacts/model-*/report.json` w `folds`.
Przed startem sprawdzana jest minimalna długość historii. Rzeczywiste dane muszą
też pokrywać te okresy. Dla początku historii pobierany jest dodatkowy kontekst
pomiarów i prognoz z trzech wcześniejszych dni, potrzebny do budowy cech.

Model użyty do predykcji musi powstać najpóźniej w chwili tej predykcji.
Tryb łączony zatrzymuje się, jeżeli nowy model nie przejdzie oceny jakości.

## Tryb i dane

`tryb` przyjmuje `"trening_i_prognoza"`, `"trening"`, `"prognoza"` albo `"ocena"`.
Do samej prognozy potrzebny jest wcześniej opublikowany model w `artefakty`.
Parametry samego modelu, farmy i opóźnienia danych ustala `konfiguracja_modelu`.

Przy `dane.prognozy_csv: null` i `dane.pomiary_csv: null` trening i predykcja
korzystają z SQL. Ustaw wcześniej zmienne `PGE_WEATHER_FORECAST_CONNECTION`
i `PGE_WEATHER_OBSERVATION_CONNECTION` według
[instrukcji SQL](START_KOREKTA_POGODY_24H.md#dane-i-połączenie-sql).
VS Code musi dziedziczyć te zmienne, np. uruchom go z przygotowanego terminala.

Dla CSV wpisz ścieżki do **obu** plików w `dane.prognozy_csv` i `dane.pomiary_csv`.
Ustaw też `separator_csv` i `rodzaj`: `"measured"`, `"synthetic"` lub `"unspecified"`.
Ścieżki względne są liczone od katalogu pliku ustawień, także przy uruchomieniu
z innego katalogu. W JSON na Windows używaj `/` albo podwójnego `\\`.
Każda historyczna predykcja odcina pomiary i wydania prognozy według swojej chwili.

Do `ocena` potrzebny jest plik pomiarów `dane.pomiary_csv` oraz zapisane
prognozy pasujące do `ocena.pliki_prognoz`. Oceniaj jedną wersję modelu naraz
i wskaż w `konfiguracja_modelu` parametry użyte do jej treningu.
Raport powstaje w `ocena.katalog_wynikow`.

## Sprawdzenie i terminal

```powershell
.\.venv\Scripts\python.exe start.py --check
.\.venv\Scripts\python.exe start.py --mode trening
.\.venv\Scripts\python.exe start.py --mode prognoza
.\.venv\Scripts\python.exe start.py --mode ocena
```

`--check` sprawdza ustawienia, zakresy i wskazane pliki, bez treningu i połączenia
z SQL. Dostęp do SQL, pokrycie danych i aktywny model są sprawdzane podczas pracy.
Możesz zachować prywatny zestaw ustawień poza repozytorium i wskazać go przez
`start.py --settings D:/moje/ustawienia.json`.

Dotychczasowe skrypty CLI zachowują działanie. Trening obsługuje dodatkowo
`--start` (dokładny początek historii; zastępuje `history_days`),
`--validation-days`, `--test-days` i `--backtest-folds`.
Ocena obsługuje `--start` i `--end`. Bezpośrednie skrypty CLI nie wczytują
`ustawienia_uruchomienia.json`; wspólną konfigurację stosuje `start.py`.
