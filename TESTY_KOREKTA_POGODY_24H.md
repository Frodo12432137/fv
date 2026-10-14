# Sprawdzenie pakietu korekty pogody v2

Weryfikacja lokalna 14 października 2026 r.: **52 testy przeszły bez ostrzeżeń**.
Pełny przepływ uczenia i predykcji sprawdzono dla XGBoost oraz
HistGradientBoosting. Sprawdzono również skrypty CLI, agregację 10 → 15 minut,
kierunek przy granicy 0/360°, dostępność danych, opóźnione odczyty, zmiany czasu,
kompletność prognoz, zapis i odczyt modelu oraz ochronę aktywnej wersji.
Publikowana wersja wymaga jawnej konfiguracji połączeń SQL; sprawdzono komunikat
błędu przy braku zmiennych środowiskowych.

Statystyki sprawdzono dla sparowanych prognoz, kołowego błędu kierunku,
brakujących pomiarów i ciszy wiatru, stałych pomiarów, zerowego błędu bazowego,
percentyli i RMSE łączonych z wielu testów oraz bloków dni w przedziale poprawy.
Sprawdzono też odcięcie dostępności późniejszych pomiarów, usuwanie powtórzonych
kopii prognoz, odrzucanie sprzecznych kopii i różnych wersji modelu oraz zapis
raportów HTML/Markdown/JSON/CSV. Raport zachowuje w liczniku pokrycia kwadranse
całkowicie pozbawione pomiarów. Strukturę tabel HTML sprawdzono parserem;
nie wykonywano wizualnej oceny w przeglądarce.

Nowe testy obejmują trajektorię tego samego otrzymanego wydania prognozy,
zanik wpływu ostatniego błędu z wyprzedzeniem, połączenie kierunków na okręgu,
odrzucanie poprawy skupionej w jednym dniu i modeli z większymi skrajnymi błędami.
Strojenie, kalibracja i test mają oddzielne okresy. Wybór produkcyjny korzysta
z najświeższej historii; dawnych testów nie przeliczamy późniejszym modelem.

## Porównanie z zachowanym pakietem v1

Benchmark używa tych samych danych syntetycznych dla obu wersji: dwóch farm,
90 dni historii, dwóch chronologicznych testów po dziewięć dni i walidacji
21 dni. Obie wersje mają 50 drzew oraz limit 8000 wierszy do dopasowania modelu.
Łącznie oceniono 19 248 wierszy na parametr w każdym scenariuszu.

Poniżej względna zmiana MAE v2 względem v1. Dodatnia wartość oznacza mniejszy
błąd v2, ujemna — większy błąd. To wyniki syntetyczne, a nie pomiary PGE.

| Scenariusz | Prędkość | Temperatura | Kierunek |
|---|---:|---:|---:|
| Stabilny błąd | +0,78% | −0,05% | −0,19% |
| Powolny dryft | +1,51% | +1,41% | +9,57% |
| Szybkie zmiany pogody | +39,16% | +44,82% | +31,18% |

v2 pomaga przede wszystkim przy zmianach pogody; przy stabilnym błędzie różnice
są małe i nie wszystkie parametry są lepsze. Eksperyment ze skróceniem
walidacji do dziewięciu dni pogorszył część wyników dryftu. Dlatego konfiguracja
produkcyjna zachowuje domyślne 21 dni, z siedmioma dniami strojenia i 14 dniami
kalibracji. Krótki przykład instalacyjny ma łagodniejsze minima i nie jest
konfiguracją do oceny skuteczności produkcyjnej.

Sprawdzono dodatkowo pierwsze 24 godziny po treningu każdej wersji,
bez przyszłych pomiarów w cechach. v2 wygenerowała 192 poprawne kwadranse
w każdym z trzech scenariuszy. MAE tej jednej doby oraz dokładne wyniki testów
są w `BENCHMARK_KOREKTA_POGODY_V2.csv`; pojedyncza doba nie wystarcza do
wnioskowania o długoterminowej przewadze.

Zachowano zgodność odczytu artefaktów v1: predykcje starego pakietu po odczycie
w v2 zgadzały się z wcześniejszym wynikiem z tolerancją 1e-7.

## Granice weryfikacji

Firmowych zapytań SQL nie wykonywano lokalnie. Nie mamy tutaj rocznej historii
pomiarów i wszystkich wydań prognoz PGE. Pierwszy trening na tych danych
wygeneruje rzeczywiste MAE, RMSE, bias i 95. percentyl błędu dla farm i horyzontów.
Wybitna skuteczność na PGE pozostaje niepotwierdzona. Bramka publikacji porównuje
kandydata z surową prognozą; sama nie dowodzi przewagi nad istniejącym modelem.

Przed oceną trzeba potwierdzić znaczenie znaczników czasu, rzeczywiste
opóźnienia dostarczenia i wysokość pomiaru wiatru względem prognozy.
Na danych syntetycznych nie można zweryfikować tych właściwości źródeł.

Środowisko: Python 3.12.14, NumPy 2.2.6, pandas 2.3.3, scikit-learn 1.9.1,
XGBoost 3.4.1, joblib 1.6.0.
