# Korekta pogody dla farm wiatrowych — 24 godziny, co 15 minut

Pakiet koryguje prędkość i kierunek wiatru oraz temperaturę względem pomiarów
meteorologicznych na farmach. Jedno uruchomienie uczenia tworzy wspólny pakiet
modeli. Jedno uruchomienie predykcji zapisuje jeden CSV z wszystkimi trzema
parametrami: 96 kwadransów dla każdej z 19 skonfigurowanych farm.

## Uruchomienie na Windows

Wymagany Python 3.11 lub 3.12 w wersji 64-bitowej oraz ODBC Driver 17 for SQL
Server. Skopiuj zawartość ZIP do katalogu, np. `D:\app\weatherCorrection_v2`.
Polecenia poniżej wykonuj w tym katalogu:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-weather.txt
Copy-Item weather_config.example.json weather_config.json
```

Uczenie (docelowo Twój job raz dziennie):

```powershell
.\.venv\Scripts\python.exe uruchom_trening_pogody.py --config weather_config.json
```

Predykcja (docelowo Twój job po otrzymaniu każdego nowego wydania prognozy):

```powershell
.\.venv\Scripts\python.exe uruchom_korekte_pogody.py
```

Domyślne ścieżki są wyznaczane względem położenia skryptów. Nie trzeba edytować
ścieżek w kodzie. Możesz przekazać `--artifacts D:\modele\pogoda` i
`--output D:\wyniki\pogoda.csv`. Oba joby muszą używać tego samego katalogu
artefaktów i tego samego środowiska Pythona.

Predykcja odczytuje ustawienia z aktywnego modelu. Jeżeli przekazujesz jej
`--config`, konfiguracja musi być identyczna z konfiguracją jego uczenia.

## Dane i połączenie SQL

Nowe zapytania znajdują się w `weather_correction/sql/`. Pobierają dane z tych
samych widoków, co dotychczasowy model. Prognozy obejmują wszystkie historyczne
wydania, z zachowanym czasem źródła i godziną prognozowaną. Zapytanie wykonania
uśrednia prędkość i temperaturę po turbinach w chwili odczytu, a kierunek
zwraca jako średnie sinusów i cosinusów. Agregacja czasowa odbywa się w Pythonie.

Skrypty wykonują tylko SELECT. Nie zapisują niczego do bazy. Daty są parametrami
ODBC; nie są wklejane do SQL ani ograniczane na stałe do konkretnego roku.

Połączenia ustaw zmiennymi środowiskowymi `PGE_WEATHER_FORECAST_CONNECTION`
i `PGE_WEATHER_OBSERVATION_CONNECTION`. Zastąp `TWOJ_SERWER` nazwą Waszego
serwera i ustaw zmienne na koncie wykonującym job. Przykład PowerShell:

```powershell
$env:PGE_WEATHER_FORECAST_CONNECTION = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=TWOJ_SERWER;DATABASE=PGESA_MarketAnalytics;Trusted_Connection=yes;"
$env:PGE_WEATHER_OBSERVATION_CONNECTION = "DRIVER={ODBC Driver 17 for SQL Server};SERVER=TWOJ_SERWER;DATABASE=PGEEO_DDS;Trusted_Connection=yes;"
```

Konto wykonujące job musi mieć uprawnienia odczytu do obu widoków. Połączenia
są wymagane wyłącznie dla SQL; tryb CSV działa bez tych zmiennych.
Własne zapytania można podać przez `--forecast-sql` i `--observation-sql`.

**Połączenie z firmową bazą i zapytania nie zostały wykonane lokalnie.**
Zweryfikowano kod i pełny przepływ na danych syntetycznych. Po pierwszym
uruchomieniu na Waszej bazie raport pokaże rzeczywistą jakość danych i korekt.

## Założenia dotyczące czasu — do dopasowania do źródła

W przykładowej konfiguracji przyjęto:

- pomiar oznacza **koniec okresu 10 minut** (`observation_timestamp_position=end`);
- pomiar jest dostępny po **20 minutach** (`observation_delay_minutes=20`);
- czas źródła prognozy jest czasem wydania, z domyślnym opóźnieniem dostarczenia
  **0 minut** (`forecast_delivery_delay_minutes=0`);
- prognozowany znacznik czasu jest **końcem kwadransa**, do którego porównujemy
  ważoną średnią pomiarów;
- `CET` w istniejących polach interpretujemy jako lokalny czas Polski,
  z uwzględnieniem zmiany czasu (`Europe/Warsaw`).

To założenia techniczne, a nie potwierdzone właściwości źródeł. Jeżeli pomiar
oznacza początek okresu, ustaw `start`; dla odczytu chwilowego ustaw `instant`.
Dla `instant` target powstaje przez interpolację między pobliskimi odczytami,
z kontrolą przerw i kołową obsługą kierunku.

Sprawdź też wysokość i typ pomiaru wiatru. Prognoza na 10 m, pomiar na maszcie
i anemometr gondoli turbiny opisują różne warunki. Model uczy się dopasowania
do wskazanych pomiarów; zmiana czujnika albo wysokości zmienia to dopasowanie.

Jeżeli `czasDanychZrodlaCET` oznacza wydanie modelu dostawcy, a paczka przychodzi
godzinę później, ustaw opóźnienie 60 minut. Najlepszym rozwiązaniem jest zwrócenie
z zapytania rzeczywistego czasu odbioru jako `available_at` w UTC. Takie pole
nadpisuje opóźnienie konfiguracyjne. Dla pomiarów również można przekazać
rzeczywiste `available_at` w UTC.

Wszystkie łączenia i okna historyczne działają w UTC. Niejednoznacznych czasów
lokalnych z powtarzanej godziny jesiennej kod nie przypisuje arbitralnie do
jednego wystąpienia: pomija te wiersze, wypisuje komunikat i liczy je w raporcie.
Eksport UTC lub z offsetem pozwala zachować oba wystąpienia godziny.

## Jak model wybiera korektę

Wersja **v2** porównuje surową prognozę, korektę błędu dla farmy i wyprzedzenia,
dwa warianty regresji Ridge oraz cztery profile XGBoost: podstawowy, płytsze
drzewa, optymalizację błędu absolutnego i trening na ostatnich 90 dniach.
Wczesna część walidacji zachowuje dwa najlepsze profile drzew dla każdego
parametru. Można ustawić `backend=hist`, aby zamiast XGBoost użyć
HistGradientBoosting ze scikit-learn.

Dodatkowo konkurują dwie korekty adaptacyjne: ostatni zaobserwowany błąd
modyfikuje wyuczony błąd farmy, a jego wpływ maleje z wyprzedzeniem prognozy.
Brak aktualnych danych pozostawia wyuczony błąd farmy. Model porównuje też
połączenia najlepszych metod; kierunki łączy na okręgu.

Prędkość i temperatura są uczone jako błędy prognozy. Kierunek jest uczony
w reprezentacji sinus/cosinus. Kierunku nie oceniamy przy zmierzonej prędkości
poniżej 1 m/s ani przy niejednoznacznej średniej kołowej. Prędkość i temperatura
pozostają oceniane niezależnie.

Cechy obejmują wartości prognozy, składowe wiatru, porę dnia, sezon,
wyprzedzenie, farmę, ostatnie dostępne pomiary oraz historyczne błędy i średnie
z ostatnich 1, 6 i 24 godzin. v2 dodaje zmienność w tych oknach, tendencję
prognozy godzinę i trzy godziny przed oraz po prognozowanym momencie,
różnicę aktualnego pomiaru względem prognozy i malejący wpływ ostatniego błędu.
Sąsiednie wartości prognozy pochodzą wyłącznie z tej samej, już otrzymanej
paczki. Pomiary i błędy muszą być znane w czasie
`available_at` danej paczki. Retry tej samej paczki używa tej samej chwili
odcięcia historii. Nie ma przesuwania wykonania względem przyszłego targetu.

Dla każdej farmy i przedziału wyprzedzenia walidacja wybiera metodę oraz siłę
korekty: 25%, 50%, 75% albo 100%. Minimalna względna poprawa MAE wynosi 1%.
Domyślnie wymagamy co najmniej siedmiu dni kalibracji. Dwudniowe bloki
losowania sprawdzają stabilność poprawy: dolna granica oszacowania z 200
próbek musi być dodatnia, a korekta musi wygrywać w co najmniej 55% dni.
Kontrolujemy również RMSE, 95. percentyl błędu i ostatnią część kalibracji.
Połączenie modeli musi dodatkowo wykazać stabilną przewagę nad najlepszym
pojedynczym modelem. Ten sprawdzian dotyczy wyboru korekty, a nie przedziału
ufności przyszłej pogody.

Za mało danych do wyboru oznacza zachowanie surowej prognozy. Brak świeżych
pomiarów dla modelu ML również oznacza surową prognozę z opisanym statusem;
nie podstawiamy do historii fikcyjnych zer.

Domyślnie uczenie używa ostatnich 365 dni. Dwa przesuwane testy obejmują po
21 dni; każdy ma wcześniejszą walidację 21 dni i wcześniejszy trening.
Pierwsze siedem dni walidacji służy do strojenia profili, a kolejne 14 dni
do wyboru metod, ich siły i połączeń. W treningu mogą być tylko etykiety znane
przed początkiem walidacji, w strojeniu tylko te znane przed kalibracją,
a w kalibracji tylko te znane przed testem. Podział obejmuje jednocześnie
wszystkie farmy. Wynik testu nie wybiera metod dla tego testu.

Publikację blokuje gorsze MAE któregokolwiek parametru w najnowszym teście
lub w łącznym wyniku wszystkich testów, pogorszenie najnowszego RMSE o ponad
1%, 95. percentyla błędu o ponad 2% albo MAE farmy i horyzontu o ponad 3%
(przy wystarczającej liczbie obserwacji). Punktem odniesienia tej bramki jest
surowa prognoza. Odrzucony kandydat ma zapisany raport i nie zastępuje
aktywnego modelu.

Po zakończeniu oceny wybór metod produkcyjnych jest odświeżany na ostatnich
21 dniach dostępnej historii, również z rozdzieleniem strojenia i kalibracji.
Wybrane modele są następnie uczone na całej dostępnej historii. Raporty testów
pozostają oceną wcześniejszych modeli: nie przeliczamy dawnych testów modelem
znającym późniejsze pomiary. Dokładna skuteczność nowego pakietu produkcyjnego
będzie znana po nadejściu kolejnych pomiarów.

Wyprzedzenie modelu jest liczone od dostępności paczki. Uczenie obejmuje do
36 godzin, aby prognoza mająca już kilka godzin mogła nadal dostarczyć wynik
na następne 24 godziny. Maksymalny dopuszczalny wiek paczki to 12 godzin.
Wynik zawsze obejmuje 96 kolejnych końców kwadransów po czasie uruchomienia.
Najnowsze wydanie musi mieć cały ten zakres; kod nie miesza go ze starszymi
wydaniami ani nie ekstrapoluje poza dostępne prognozy.

W przypadku prognoz godzinowych interpolacja do kwadransów odbywa się tylko
wewnątrz jednego wydania, w składowych wiatru i temperaturze, maksymalnie przez
przerwę 60 minut. Daje to wynik co 15 minut, lecz nie oznacza, że wejściowa
prognoza ma niezależną informację dla każdego kwadransa.

## Wyniki i raporty

`weather_output/prognoza_pogody_korekta_24h.csv` zawiera wartości surowe,
skorygowane i korekty dla trzech parametrów. Zachowuje nazwy kolumn
`skorygowana_predkoscWiatru`, `skorygowany_kierunekWiatru` i
`skorygowana_temperatura`. Prędkość jest w m/s, kierunek w stopniach
meteorologicznych (skąd wieje), temperatura w °C.

CSV zawiera też kod i nazwę farmy, czas UTC i lokalny z offsetem, wydanie,
dostępność paczki, czas predykcji, wersję modelu, wybraną metodę i status dla
każdego parametru. `wiekPomiaruMinuty` oznacza wiek w chwili dostępności paczki,
czyli względem chwili odcięcia jej historii.

Każda wersja w `weather_artifacts/model-.../` ma:

- `model.joblib` — wspólny pakiet modeli i przetwarzania;
- `report.json` — ustawienia, wersje bibliotek, okresy testów, strojenie profili,
  odświeżony wybór produkcyjny i przyczyny odrzucenia publikacji;
- `test_metrics.csv` — MAE, RMSE, bias i 95. percentyl błędu dla każdego
  parametru, farmy, horyzontu i testu;
- `validation_candidates.csv` — porównanie metod i połączeń, stabilność poprawy,
  odsetek lepszych dni; rekordy `fold=production` opisują najświeższy wybór;
- `routes.json` — wybrane metody dla farm i horyzontów.

Każdy trening zapisuje również `model_statistics.html`, `.md`, `.json`, `.csv`
oraz `daily_statistics.csv`. Raport obejmuje dodatkowe percentyle, R² dla
parametrów liniowych, częstość poprawy, pokrycie pomiarów i diagnostyczny
przedział poprawy MAE. Szczegóły i skrypt oceny zapisanych prognoz są opisane
w [STATYSTYKI_MODELU.md](STATYSTYKI_MODELU.md).

Aktywną wersję wskazuje atomowo zapisany `current.json`. Predykcja sprawdza
sumę kontrolną modelu. Błąd pobrania, niepełna prognoza albo wadliwe dane
nie nadpisują wcześniejszego CSV. Odbiorca wyniku powinien sprawdzać powodzenie
joba i zapisany czas predykcji.

Kod zakończenia: `0` sukces; `1` błąd danych/konfiguracji/połączenia; `2`
uczenie ukończone, ale kandydat nie przeszedł bramki publikacji. Jeśli nie było
wcześniej aktywnego modelu, predykcja
nie wystartuje po kodzie `2`.

## CSV i sprawdzenie instalacji

Minimalne wejście prognozy:

```text
farm,issued_at,available_at,valid_at,speed,direction,temperature
GAL,2026-10-14T04:00:00Z,2026-10-14T05:00:00Z,2026-10-14T06:15:00Z,8.2,359,12.5
```

Minimalne wejście pomiarów (tutaj dostępność można pominąć, stosując opóźnienie
z konfiguracji):

```text
farm,observed_at,speed,direction,temperature
GAL,2026-10-14T04:50:00Z,7.5,1,11.8
```

Eksport treningowy musi zawierać historię wszystkich wydań, a nie wynik
starego zapytania z `rn=1`. Nazwy farm mogą być kodami albo nazwami z istniejących
widoków. Nie należy używać kierunku już uśrednionego arytmetycznie w starym SQL.

Przykład pracy na własnych CSV:

```powershell
.\.venv\Scripts\python.exe uruchom_trening_pogody.py --config weather_config.json --forecast-csv prognozy.csv --observation-csv pomiary.csv
.\.venv\Scripts\python.exe uruchom_korekte_pogody.py --forecast-csv prognozy_nowe_i_historia_3dni.csv --observation-csv pomiary_3dni.csv
```

Dla CSV rozdzielanego średnikiem dodaj `--csv-separator ";"`. Dla testu
historycznego podaj `--as-of` z offsetem. Model musi być uczony najpóźniej
w tej chwili, aby nie oceniać przeszłości modelem znającym późniejsze dane.

Przykład syntetyczny do sprawdzenia całej instalacji:

```powershell
.\.venv\Scripts\python.exe -m weather_correction.demo
.\.venv\Scripts\python.exe uruchom_trening_pogody.py --config weather_demo\config.json --forecast-csv weather_demo\forecasts.csv --observation-csv weather_demo\observations.csv --as-of 2026-04-11T00:00:00Z --artifacts weather_demo\models
.\.venv\Scripts\python.exe uruchom_korekte_pogody.py --forecast-csv weather_demo\forecasts.csv --observation-csv weather_demo\observations.csv --as-of 2026-04-11T00:00:00Z --artifacts weather_demo\models --output weather_demo\wynik.csv
```

Przykład dotyczy dwóch farm i danych wymyślonych. Jego błędy nie są wynikiem
na historii PGE. Aby uruchomić testy, zainstaluj `pytest` i wykonaj:

```powershell
.\.venv\Scripts\python.exe -m pytest tests -q
```

Na macOS XGBoost wymaga OpenMP (`brew install libomp`). W lokalnym środowisku
testowym można też udostępnić bibliotekę OpenMP dostarczoną ze scikit-learn
przez `DYLD_LIBRARY_PATH`. Nie jest to wymagane w poleceniach Windows powyżej.

## Porównanie z v1

Pakiet zawiera powtarzalny benchmark trzech scenariuszy syntetycznych:
stabilnego błędu, powolnego dryftu i przesunięcia szybkich zmian pogody.
Wymaga zachowanego ZIP v1:

```powershell
.\.venv\Scripts\python.exe -m weather_correction.benchmark --previous-version ..\pge_korekta_pogody_24h_v1.zip
```

Obie wersje dostają identyczne dane i okresy testów. `comparison.csv` zawiera
ważone MAE dwóch testów oraz osobną ocenę pierwszych 24 godzin po treningu.
Domyślna walidacja ma 21 dni, jak konfiguracja produkcyjna; dla szybszego
sprawdzenia benchmark używa 50 drzew i maksymalnie 8000 wierszy treningowych.
To test zachowania metod na wymyślonych danych, a nie dowód skuteczności na PGE.

Istniejące artefakty v1 można nadal odczytywać: zachowują dawne cechy i ich
znaczenie. Nowe uczenie domyślnie korzysta z cech v2.

## Podstawa metody

- [ECMWF: korekta błędów temperatury i prędkości wiatru](https://www.ecmwf.int/en/elibrary/81297-statistical-modelling-2m-temperature-and-10m-wind-speed-forecast-errors)
- [FMI: operacyjna korekta meteorologiczna oparta na XGBoost](https://rmets.onlinelibrary.wiley.com/doi/10.1002/met.70074)
- [scikit-learn: ocena szeregów czasowych z cechami historycznymi](https://scikit-learn.org/stable/auto_examples/applications/plot_time_series_lagged_features.html)

Rzeczywistą przewagę nowego rozwiązania nad surową prognozą oceni raport
z Waszej historii. Przyjęte progi i domyślne parametry są punktem startowym;
zmiany należy oceniać na kolejnych okresach, zachowując niezależny test.
