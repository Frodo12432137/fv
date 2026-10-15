"""Otwórz ten plik w VS Code i kliknij ▶ Uruchom plik Python.

Daty, tryb pracy i ścieżki zmieniaj w ustawienia_uruchomienia.json.
"""

if __name__ == "__main__":
    try:
        from weather_correction.runner import main
    except ModuleNotFoundError as exc:
        print(f"Brak biblioteki: {exc.name}. Wybierz interpreter .venv w VS Code i wykonaj:\n"
              "python -m pip install -r requirements-weather.txt")
        raise SystemExit(1)
    raise SystemExit(main())
