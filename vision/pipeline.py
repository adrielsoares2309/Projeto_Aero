"""Coordenação explícita do processamento e treinamento de visão."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (accuracy_score, classification_report, confusion_matrix,
                             f1_score, precision_score, recall_score)
from sklearn.model_selection import train_test_split

from .geometry import GeometryConfig, analyze_geometry, load_image
from .thermal import ThermalConfig, analyze_thermal

SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".tif", ".tiff", ".webp"}
CLASS_NAMES = {"normal", "defeituosa", "defeituosas", "defeito", "defect", "fault", "anormal"}


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def identify_type(path: Path, explicit_type: str | None = None) -> str | None:
    """Resolve tipo por escolha explícita ou nomes contextuais claros."""
    if explicit_type:
        if explicit_type not in {"geometrica", "termica"}:
            raise ValueError("explicit_type deve ser 'geometrica' ou 'termica'")
        return explicit_type
    tokens = {part.casefold() for part in path.parts} | {path.stem.casefold()}
    thermal = any(any(key in token for key in ("termica", "termico", "thermal", "infrared", "hotspot", "turbina_")) for token in tokens)
    geometric = any(any(key in token for key in ("geometr", "geo_", "rotor", "eixo", "pa_")) for token in tokens)
    if thermal != geometric:
        return "termica" if thermal else "geometrica"
    return None


def _output_stem(source: Path, root: Path) -> str:
    relative = str(source.resolve()).encode("utf-8", errors="replace")
    return f"{source.stem}_{hashlib.sha256(relative).hexdigest()[:10]}"


def process_image(path: str | Path, image_type: str | None = None,
                  output_root: str | Path | None = None,
                  geometry_config: GeometryConfig | None = None,
                  thermal_config: ThermalConfig | None = None) -> dict[str, Any]:
    source = Path(path)
    kind = identify_type(source, image_type)
    if kind is None:
        return {"path": str(source), "status": "unclassified", "type": None,
                "warnings": ["Tipo de imagem ambíguo; informe image_type explicitamente."], "errors": []}
    base = Path(output_root) if output_root is not None else project_root() / "data" / "processed" / "imagens"
    dest = base / ("geometricas" if kind == "geometrica" else "termicas")
    dest.mkdir(parents=True, exist_ok=True)
    # Directory per unique source avoids collisions between equal basenames.
    dest = dest / _output_stem(source, project_root())
    result = analyze_geometry(source, dest, geometry_config) if kind == "geometrica" else analyze_thermal(source, dest, thermal_config)
    return {"type": kind, "status": "processed", **result}


def discover_images(input_root: str | Path | None = None) -> tuple[list[Path], list[Path]]:
    root = Path(input_root) if input_root is not None else project_root() / "data" / "raw" / "imagens"
    if not root.exists():
        return [], []
    files = sorted(p for p in root.rglob("*") if p.is_file())
    return [p for p in files if p.suffix.lower() in SUPPORTED_EXTENSIONS], [p for p in files if p.suffix.lower() not in SUPPORTED_EXTENSIONS]


def process_batch(input_root: str | Path | None = None, output_root: str | Path | None = None,
                  type_overrides: dict[str, str] | None = None,
                  label_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """Processa em lote isolando falhas e grava JSON cumulativo."""
    root = Path(input_root) if input_root is not None else project_root() / "data" / "raw" / "imagens"
    out = Path(output_root) if output_root is not None else project_root() / "data" / "processed" / "imagens"
    images, unsupported = discover_images(root)
    results: list[dict[str, Any]] = []
    for source in images:
        override = (type_overrides or {}).get(str(source), (type_overrides or {}).get(source.name))
        try:
            result = process_image(source, override, out)
            label = (label_overrides or {}).get(str(source), (label_overrides or {}).get(source.name))
            if label is not None:
                result["user_provided_label"] = label
            results.append(result)
        except Exception as exc:  # batch continues and records per-file failure
            results.append({"path": str(source), "status": "failed", "type": override,
                            "warnings": [], "errors": [f"{type(exc).__name__}: {exc}"]})
    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "input_root": str(root), "total_images_found": len(images) + len(unsupported),
        "supported_images": len(images), "processed": sum(r["status"] == "processed" for r in results),
        "geometric_images": sum(r.get("type") == "geometrica" and r["status"] == "processed" for r in results),
        "thermal_images": sum(r.get("type") == "termica" and r["status"] == "processed" for r in results),
        "ignored": len(unsupported) + sum(r["status"] == "unclassified" for r in results),
        "failures": sum(r["status"] == "failed" for r in results),
        "unsupported_files": [str(p) for p in unsupported], "results": results,
        "dataset_diagnostic": diagnose_image_dataset(root),
        "training": inspect_training_data(root, label_overrides=label_overrides),
    }
    out.mkdir(parents=True, exist_ok=True)
    report = out / "resultados.json"
    report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    summary["report_path"] = str(report)
    return summary


def _class_for_image(path: Path, label_overrides: dict[str, str] | None = None) -> str | None:
    # Accept caller-supplied labels or explicit class directory names only.
    override = (label_overrides or {}).get(str(path), (label_overrides or {}).get(path.name))
    if override is not None:
        return str(override).strip().casefold() or None
    for parent in path.parents:
        label = parent.name.casefold()
        if label in CLASS_NAMES:
            return label
        if parent == parent.parent:
            break
    tokens = set(re.split(r"[^a-z0-9]+", path.stem.casefold()))
    if tokens.intersection({"superaquecimento", "aquecimento", "overheating"}):
        return "superaquecimento"
    if any(token.startswith(("defeituos", "deformad", "defect", "tort")) for token in tokens):
        return "defeituosa"
    if "normal" in tokens:
        return "normal"
    return None


def diagnose_image_dataset(input_root: str | Path | None = None) -> dict[str, Any]:
    """Resume arquivos, modalidades, rótulos explícitos, dimensões e duplicatas."""
    root = Path(input_root) if input_root is not None else project_root() / "data" / "raw" / "imagens"
    supported, unsupported = discover_images(root)
    modality_counts = {"geometrica": 0, "termica": 0, "nao_classificada": 0}
    class_counts: dict[str, dict[str, int]] = {}
    dimensions: dict[str, int] = {}
    invalid: list[str] = []
    hashes: dict[str, list[str]] = {}
    perceptual_hashes: list[tuple[str, int]] = []
    for path in supported:
        modality = identify_type(path)
        modality_counts[modality or "nao_classificada"] += 1
        label = _class_for_image(path)
        if label:
            bucket = class_counts.setdefault(modality or "nao_classificada", {})
            bucket[label] = bucket.get(label, 0) + 1
        try:
            raw = np.frombuffer(path.read_bytes(), dtype=np.uint8)
            image = cv2.imdecode(raw, cv2.IMREAD_UNCHANGED)
            if image is None or image.size == 0:
                invalid.append(str(path))
                continue
            size = f"{image.shape[1]}x{image.shape[0]}"
            dimensions[size] = dimensions.get(size, 0) + 1
            digest = hashlib.sha256(raw).hexdigest()
            hashes.setdefault(digest, []).append(str(path))
            gray = cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY) if image.ndim == 3 else image
            reduced = cv2.resize(gray, (32, 32), interpolation=cv2.INTER_AREA).astype(np.float32)
            low_frequency = cv2.dct(reduced)[:8, :8]
            coefficients = low_frequency.flatten()[1:]
            median = float(np.median(coefficients))
            perceptual = sum(1 << index for index, value in enumerate(coefficients) if value > median)
            perceptual_hashes.append((str(path), perceptual))
        except OSError:
            invalid.append(str(path))
    duplicates = [paths for paths in hashes.values() if len(paths) > 1]
    near_duplicates = []
    for index, (first, first_hash) in enumerate(perceptual_hashes):
        for second, second_hash in perceptual_hashes[index + 1:]:
            if (first_hash ^ second_hash).bit_count() <= 4 and first not in next((group for group in duplicates if second in group), []):
                near_duplicates.append({"first": first, "second": second, "hash_distance": (first_hash ^ second_hash).bit_count()})
    return {"total_files": len(supported) + len(unsupported), "supported_images": len(supported),
            "modality_counts": modality_counts, "class_counts": class_counts,
            "dimensions": dimensions, "invalid_files": invalid,
            "unsupported_files": [str(p) for p in unsupported], "exact_duplicates": duplicates,
            "near_duplicate_candidates": near_duplicates,
            "limitations": ["Dataset pequeno; não há imagens suficientes por classe para validar ML."]}


def inspect_training_data(input_root: str | Path | None = None,
                          label_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    root = Path(input_root) if input_root is not None else project_root() / "data" / "raw" / "imagens"
    images, _ = discover_images(root)
    classes: dict[str, dict[str, int]] = {}
    for path in images:
        label = _class_for_image(path, label_overrides)
        modality = identify_type(path)
        if label and modality:
            bucket = classes.setdefault(modality, {})
            bucket[label] = bucket.get(label, 0) + 1
    ready_by_modality = {
        modality: len(counts) >= 2 and min(counts.values(), default=0) >= 4
        for modality, counts in classes.items()
    }
    ready = bool(ready_by_modality) and all(ready_by_modality.values())
    return {"class_counts_by_modality": classes,
            "labeled_images": sum(sum(counts.values()) for counts in classes.values()),
            "ready_by_modality": ready_by_modality,
            "ready_for_supervised_training": ready,
            "diagnostic": None if ready else "Treinamento supervisionado não executado: são necessárias pelo menos duas classes com quatro imagens rotuladas por classe para uma divisão treino/teste mínima."}


def _feature_vector_from_image(image: np.ndarray, modality: str) -> np.ndarray:
    if image.ndim == 2:
        gray = image
        bgr = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
    else:
        bgr = image[:, :, :3]
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(gray, (64, 64))
    # Cell-based HOG using portable Sobel operations; avoids relying on
    # cv2.HOGDescriptor, absent in some otherwise valid OpenCV builds.
    gx = cv2.Sobel(small, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(small, cv2.CV_32F, 0, 1, ksize=3)
    magnitude, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)
    angle %= 180.0
    hog_cells = []
    for y in range(0, 64, 8):
        for x in range(0, 64, 8):
            hist, _ = np.histogram(angle[y:y + 8, x:x + 8], bins=9,
                                   range=(0, 180), weights=magnitude[y:y + 8, x:x + 8])
            hog_cells.append(hist.astype(np.float32))
    hog = np.concatenate(hog_cells)
    hog /= max(float(np.linalg.norm(hog)), 1e-8)
    if modality == "geometrica":
        return np.concatenate([hog, np.array([float(gray.mean()), float(gray.std())])])
    if modality == "termica":
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        return np.concatenate([hog, hsv.reshape(-1, 3).mean(axis=0), hsv.reshape(-1, 3).std(axis=0)])
    raise ValueError("modality deve ser geometrica ou termica")


def _feature_vector(path: Path, modality: str) -> np.ndarray:
    return _feature_vector_from_image(load_image(path), modality)


def predict_image(image: np.ndarray, modality: str,
                  model_dir: str | Path | None = None,
                  min_confidence: float = 0.60) -> dict[str, Any]:
    """Prediz apenas com artefato próprio da modalidade e metadados avaliados."""
    if modality not in {"geometrica", "termica"}:
        raise ValueError("modality deve ser geometrica ou termica")
    if not 0.0 <= min_confidence <= 1.0:
        raise ValueError("min_confidence deve estar entre 0 e 1")
    directory = Path(model_dir) if model_dir is not None else project_root() / "data" / "processed" / "imagens" / "modelos"
    model_path = directory / f"{modality}_classifier.joblib"
    metadata_path = directory / f"{modality}_classifier_metadata.json"
    if not model_path.exists() or not metadata_path.exists():
        return {"available": False, "class": "indeterminada", "reason": "Não há modelo treinado e validado para esta modalidade."}
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        payload = joblib.load(model_path)
        if payload.get("modality") != modality or metadata.get("modality") != modality:
            raise ValueError("O artefato não corresponde à modalidade selecionada.")
        if not metadata.get("metrics") or not metadata.get("classes"):
            raise ValueError("O modelo não contém métricas de validação e classes compatíveis.")
        model = payload["model"]
        vector = _feature_vector_from_image(image, modality).reshape(1, -1)
        if hasattr(model, "predict_proba"):
            probabilities = model.predict_proba(vector)[0]
            classes = list(model.classes_)
            index = int(np.argmax(probabilities))
            confidence = float(probabilities[index])
            predicted = str(classes[index])
            state = predicted if confidence >= min_confidence else "indeterminada"
            return {"available": True, "class": state, "model_class": predicted,
                    "confidence": confidence, "threshold": min_confidence,
                    "method": "ML", "model_path": str(model_path)}
        predicted = str(model.predict(vector)[0])
        return {"available": True, "class": predicted, "method": "ML",
                "confidence": None, "model_path": str(model_path)}
    except Exception as exc:
        return {"available": False, "class": "indeterminada",
                "reason": f"Modelo indisponível ou incompatível: {exc}"}


def train_classifier(input_root: str | Path | None = None, modality: str = "geometrica",
                     model_dir: str | Path | None = None, test_size: float = 0.25,
                     random_state: int = 42,
                     label_overrides: dict[str, str] | None = None) -> dict[str, Any]:
    """Treina RF apenas com rótulos em diretórios e avalia em holdout estratificado."""
    if not 0 < test_size < 1:
        raise ValueError("test_size deve estar entre 0 e 1")
    root = Path(input_root) if input_root is not None else project_root() / "data" / "raw" / "imagens"
    images, _ = discover_images(root)
    # The modality must be explicit when filenames do not identify it reliably.
    explicit_thermal = {str(k) for k, v in (label_overrides or {}).items() if v}
    selected = [(p, _class_for_image(p, label_overrides)) for p in images
                if identify_type(p) == modality or (modality == "termica" and (p.name in explicit_thermal or str(p) in explicit_thermal))]
    selected = [(p, y) for p, y in selected if y is not None]
    counts: dict[str, int] = {}
    for _, label in selected:
        counts[label] = counts.get(label, 0) + 1
    if len(counts) < 2 or min(counts.values(), default=0) < 4:
        return {"trained": False, "reason": "Classes explícitas insuficientes: exige pelo menos duas classes e quatro imagens por classe para holdout.", "class_counts": counts}
    X = np.vstack([_feature_vector(path, modality) for path, _ in selected])
    y = np.array([label for _, label in selected])
    if not np.isfinite(X).all():
        return {"trained": False, "reason": "Características contêm valores não finitos.", "class_counts": counts}
    try:
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=test_size, random_state=random_state, stratify=y)
    except ValueError as exc:
        return {"trained": False, "reason": f"Divisão treino/teste inviável: {exc}", "class_counts": counts}
    model = RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=random_state)
    model.fit(X_train, y_train)
    pred = model.predict(X_test)
    labels = sorted(set(y.tolist()))
    metrics = {"accuracy": float(accuracy_score(y_test, pred)),
               "precision_macro": float(precision_score(y_test, pred, average="macro", zero_division=0)),
               "recall_macro": float(recall_score(y_test, pred, average="macro", zero_division=0)),
               "f1_macro": float(f1_score(y_test, pred, average="macro", zero_division=0)),
               "confusion_matrix": confusion_matrix(y_test, pred, labels=labels).tolist(),
               "classification_report": classification_report(y_test, pred, labels=labels, output_dict=True, zero_division=0)}
    dest = Path(model_dir) if model_dir is not None else project_root() / "data" / "processed" / "imagens" / "modelos"
    dest.mkdir(parents=True, exist_ok=True)
    payload = {"model": model, "modality": modality, "feature_count": int(X.shape[1]), "classes": labels, "feature_method": "HOG 64x64 + modality summary", "pipeline_version": "1.0"}
    model_path = dest / f"{modality}_classifier.joblib"
    metadata_path = dest / f"{modality}_classifier_metadata.json"
    joblib.dump(payload, model_path)
    metadata = {"trained_at_utc": datetime.now(timezone.utc).isoformat(), "modality": modality,
                "classes": labels, "class_counts": counts, "train_samples": len(y_train), "test_samples": len(y_test),
                "metrics": metrics, "test_size": test_size, "random_state": random_state,
                "feature_method": payload["feature_method"], "model_path": str(model_path)}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"trained": True, "metadata": metadata, "metadata_path": str(metadata_path)}
