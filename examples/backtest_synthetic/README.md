# Przykład backtestu kroczącego — dane syntetyczne

To wynik sprawdzenia programu, **nie skuteczność na farmach PGE**.
Generator `synthetic_sources(days=40, farm_codes=("GAL",))` tworzy wymyślone
prognozy i pomiary o stabilnym, łatwym do skorygowania błędzie.

Pierwszy model uczy się na 2026-01-01–2026-02-02 UTC. Backtest obejmuje
2026-02-02–2026-02-10 UTC, z pomiarami dostępnymi do 2026-02-11 UTC.
Uczenie jest odświeżane co dobę, a prognozy co sześć godzin. Osiem uczeń
i 32 prognozy utworzyły 2924 oceniane kwadranse na parametr po ograniczeniu
do wybranego okresu. Te wiersze obejmują także różne prognozy tego samego
pomiaru z różnymi wyprzedzeniami; nie są 2924 niezależnymi pomiarami.

Konfiguracja przykładu: HistGradientBoosting, sześć drzew, jeden profil drzew,
limit 2000 wierszy do dopasowania, walidacja trzy dni, jeden test trzydniowy,
minimalna historia treningowa siedem dni, minimalna liczba dni kalibracji dwa,
40 próbek sprawdzania stabilności wyboru korekt, jeden wątek. Pozostałe
ustawienia pochodzą z `Settings()` v2.2. To szybki test przepływu, nie ustawienia
do wnioskowania o jakości produkcyjnej.

[Wynik i tabela błędów](BACKTEST.md) · [Pełne statystyki](model_statistics.md)

CSV dzienników zachowują nazwy lokalnych plików prognoz, logów i modeli.
Same te pliki nie są publikowane w tym przykładzie. Wyniki rzeczywistego
wykonania w środowisku firmowym znajdą się w lokalnym katalogu wybranego runu.
