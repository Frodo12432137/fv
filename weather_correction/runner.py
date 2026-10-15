"""Uruchamianie z jednego pliku ustawień, także bez argumentów w VS Code."""
from __future__ import annotations

import argparse
import glob
import json
import sys
from dataclasses import replace
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from .cli import predict_main, train_main
from .config import Settings
from .data import utc_time


ROOT = Path(__file__).resolve().parent.parent
MODES = ("trening_i_prognoza", "trening", "prognoza", "ocena")


def build_commands(settings_path: Path, mode: str | None = None, now=None) -> list[tuple[str, list[str]]]:
    """Sprawdź całą konfigurację przed uczeniem lub zapisem wyników."""
    data = json.loads(settings_path.read_text(encoding="utf-8-sig"))
    sections = {
        "": {"tryb", "strefa_czasowa", "konfiguracja_modelu", "artefakty", "dane", "trening", "prognoza", "ocena"},
        "dane": {"prognozy_csv", "pomiary_csv", "separator_csv", "rodzaj"},
        "trening": {"start", "koniec", "dni_walidacji", "dni_testu", "liczba_testow"},
        "prognoza": {"start", "koniec", "krok_godziny", "katalog_wynikow"},
        "ocena": {"start", "koniec", "pomiary_dostepne_do", "pliki_prognoz", "katalog_wynikow"},
    }
    for section, keys in sections.items():
        values = data if not section else data.get(section)
        if not isinstance(values, dict) or set(values) != keys:
            raise ValueError(f"Niepoprawne pola sekcji {section or 'głównej'}. Wymagane: {', '.join(sorted(keys))}.")
    mode = mode or data["tryb"]
    if mode not in MODES:
        raise ValueError(f"tryb: wybierz {', '.join(MODES)}.")
    timezone = data["strefa_czasowa"]
    ZoneInfo(timezone)
    now = pd.Timestamp.now(tz="UTC") if now is None else utc_time(now, timezone)

    def stamp(value, label):
        if value is None:
            return None
        try:
            if not isinstance(value, str) or not value.strip():
                raise ValueError("Data musi być tekstem albo null.")
            result = utc_time(value, timezone)
            if pd.isna(result):
                raise ValueError("NaT")
            return result
        except Exception as exc:
            raise ValueError(f"Niepoprawna data {label}: {value!r}. Użyj np. 2026-10-15T06:00:00+02:00.") from exc

    def path(value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Ścieżka musi być niepustym tekstem.")
        result = Path(value)
        return result if result.is_absolute() else settings_path.resolve().parent / result

    def input_path(value):
        result = path(value)
        if not result.is_file():
            raise ValueError(f"Brak pliku: {result}")
        return str(result)

    source = data["dane"]
    if source["rodzaj"] not in ("unspecified", "measured", "synthetic"):
        raise ValueError("dane.rodzaj: unspecified, measured albo synthetic.")
    if not isinstance(source["separator_csv"], str) or len(source["separator_csv"]) != 1:
        raise ValueError("dane.separator_csv musi być pojedynczym znakiem.")
    common = ["--artifacts", str(path(data["artefakty"])), "--csv-separator", source["separator_csv"]]
    if mode != "ocena":
        if (source["prognozy_csv"] is None) != (source["pomiary_csv"] is None):
            raise ValueError("Ustaw oba pola dane.prognozy_csv i dane.pomiary_csv albo oba na null (SQL).")
        if source["prognozy_csv"] is not None:
            common += ["--forecast-csv", input_path(source["prognozy_csv"]),
                       "--observation-csv", input_path(source["pomiary_csv"])]

    commands = []
    training_end = None
    if mode in ("trening", "trening_i_prognoza"):
        training = data["trening"]
        start = stamp(training["start"], "trening.start")
        training_end = stamp(training["koniec"], "trening.koniec")
        if training_end is None:
            training_end = now
        if start is not None and start >= training_end:
            raise ValueError("trening.start musi być wcześniejszy niż trening.koniec.")
        model_config = input_path(data["konfiguracja_modelu"])
        for key in ("dni_walidacji", "dni_testu", "liczba_testow"):
            if type(training[key]) is not int or training[key] <= 0:
                raise ValueError(f"trening.{key} musi być dodatnią liczbą całkowitą.")
        cfg = replace(Settings.load(model_config), validation_days=training["dni_walidacji"],
                      test_days=training["dni_testu"], backtest_folds=training["liczba_testow"])
        history_start = start if start is not None else training_end - pd.Timedelta(days=cfg.history_days)
        minimum = cfg.validation_days + cfg.test_days * cfg.backtest_folds + cfg.min_training_days
        if training_end - history_start < pd.Timedelta(days=minimum):
            raise ValueError(f"Historia jest za krótka. Potrzeba co najmniej {minimum} dni na trening, walidację i testy.")
        args = common + ["--config", model_config, "--as-of", training_end.isoformat(),
                         "--validation-days", str(cfg.validation_days), "--test-days", str(cfg.test_days),
                         "--backtest-folds", str(cfg.backtest_folds), "--data-kind", source["rodzaj"]]
        if start is not None:
            args += ["--start", start.isoformat()]
        commands.append(("trening", args))

    if mode in ("prognoza", "trening_i_prognoza"):
        prediction = data["prognoza"]
        start = stamp(prediction["start"], "prognoza.start")
        if start is None:
            start = training_end if training_end is not None else now
        end = stamp(prediction["koniec"], "prognoza.koniec")
        if end is not None and start >= end:
            raise ValueError("prognoza.start musi być wcześniejszy niż prognoza.koniec.")
        if training_end is not None and start < training_end:
            raise ValueError("Prognozowanie musi zaczynać się po zakończeniu uczenia albo dokładnie w tej chwili.")
        step = prediction["krok_godziny"]
        if type(step) is not int or step <= 0:
            raise ValueError("prognoza.krok_godziny musi być dodatnią liczbą całkowitą.")
        output_dir = path(prediction["katalog_wynikow"])
        current = start
        while end is None or current < end:
            output = output_dir / f"prognoza_{current.strftime('%Y%m%dT%H%M%S%fZ')}.csv"
            commands.append(("prognoza", common + ["--as-of", current.isoformat(), "--output", str(output)]))
            if end is None:
                break
            current += pd.Timedelta(hours=step)

    if mode == "ocena":
        evaluation = data["ocena"]
        start = stamp(evaluation["start"], "ocena.start")
        end = stamp(evaluation["koniec"], "ocena.koniec")
        as_of = stamp(evaluation["pomiary_dostepne_do"], "ocena.pomiary_dostepne_do")
        if start is not None and end is not None and start >= end:
            raise ValueError("ocena.start musi być wcześniejszy niż ocena.koniec.")
        if source["pomiary_csv"] is None:
            raise ValueError("Do oceny ustaw dane.pomiary_csv na plik pomiarów.")
        files = sorted(glob.glob(str(path(evaluation["pliki_prognoz"]))))
        if not files:
            raise ValueError("Nie znaleziono plików z ocena.pliki_prognoz. Najpierw wygeneruj prognozy.")
        args = ["--config", input_path(data["konfiguracja_modelu"]), "--predictions-csv", *files,
                "--observation-csv", input_path(source["pomiary_csv"]),
                "--csv-separator", source["separator_csv"], "--data-kind", source["rodzaj"],
                "--output", str(path(evaluation["katalog_wynikow"])),
                "--as-of", (as_of if as_of is not None else now).isoformat()]
        for flag, value in (("--start", start), ("--end", end)):
            if value is not None:
                args += [flag, value.isoformat()]
        commands.append(("ocena", args))
    return commands


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--settings", type=Path, default=ROOT / "ustawienia_uruchomienia.json")
    parser.add_argument("--mode", choices=MODES, help="Nadpisz tryb z pliku ustawień.")
    parser.add_argument("--check", action="store_true", help="Sprawdź ustawienia bez wykonywania obliczeń i łączenia z SQL.")
    args = parser.parse_args(argv)
    try:
        commands = build_commands(args.settings, args.mode)
        print(f"Ustawienia: {args.settings.resolve()}", flush=True)
        for mode in ("trening", "prognoza", "ocena"):
            count = sum(kind == mode for kind, _ in commands)
            if count:
                print(f"Plan: {mode}, liczba uruchomień: {count}.", flush=True)
        if args.check:
            print("Ustawienia poprawne. Dostęp do danych i modelu jest sprawdzany przy właściwym uruchomieniu.")
            return 0
        from ocen_prognoze_pogody import main as evaluate_main
        handlers = {"trening": train_main, "prognoza": predict_main, "ocena": evaluate_main}
        for index, (mode, command_args) in enumerate(commands, 1):
            print(f"\n[{index}/{len(commands)}] {mode}", flush=True)
            code = handlers[mode](command_args)
            if code:
                print(f"Przerwano: {mode} zakończył się kodem {code}. Sprawdź komunikat powyżej.", file=sys.stderr)
                return code
        print("Gotowe.", flush=True)
        return 0
    except Exception as exc:
        print(f"BŁĄD ustawień: {exc}", file=sys.stderr, flush=True)
        return 1
