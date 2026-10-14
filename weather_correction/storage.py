from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

import joblib
import pandas as pd


def atomic_json(path: Path, content: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_csv(path: Path, content: pd.DataFrame):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        content.to_csv(temp, index=False, encoding="utf-8-sig")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def atomic_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def save_assessment(folder: Path, assessment: dict):
    from .evaluation import render_html, render_markdown
    atomic_json(folder / "model_statistics.json", assessment)
    atomic_csv(folder / "model_statistics.csv", pd.DataFrame(assessment["metrics"]))
    atomic_csv(folder / "daily_statistics.csv", pd.DataFrame(assessment["daily_metrics"]))
    atomic_text(folder / "model_statistics.md", render_markdown(assessment))
    atomic_text(folder / "model_statistics.html", render_html(assessment))


def save_bundle(root: Path, bundle: dict, report: dict, test_rows: list, selection_rows: list,
                publish: bool, assessment: dict | None = None) -> Path:
    version = "model-" + pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    folder = root / version
    folder.mkdir(parents=True, exist_ok=False)
    model_path = folder / "model.joblib"
    joblib.dump(bundle, model_path, compress=3)
    atomic_json(folder / "report.json", report)
    atomic_csv(folder / "test_metrics.csv", pd.DataFrame(test_rows))
    atomic_csv(folder / "validation_candidates.csv", pd.DataFrame(selection_rows))
    atomic_json(folder / "routes.json", bundle["routes"])
    if assessment is not None:
        save_assessment(folder, assessment)
    digest = hashlib.sha256(model_path.read_bytes()).hexdigest()
    if publish:
        atomic_json(root / "current.json", {"version": version, "sha256": digest, "format_version": 1})
    return folder


def load_bundle(root: Path) -> tuple[dict, str]:
    pointer = root / "current.json"
    if not pointer.exists():
        raise ValueError("Brak aktywnego modelu (current.json). Najpierw uruchom uczenie.")
    manifest = json.loads(pointer.read_text(encoding="utf-8"))
    version = manifest["version"]
    if Path(version).name != version or not version.startswith("model-"):
        raise ValueError("Niepoprawna ścieżka wersji modelu.")
    model = root / version / "model.joblib"
    if hashlib.sha256(model.read_bytes()).hexdigest() != manifest["sha256"]:
        raise ValueError("Suma kontrolna modelu nie zgadza się z manifestem.")
    bundle = joblib.load(model)
    if bundle.get("format_version") != 1:
        raise ValueError("Nieobsługiwany format artefaktu modelu.")
    return bundle, version
