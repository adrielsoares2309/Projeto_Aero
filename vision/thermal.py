"""Segmentação qualitativa de regiões coloridas candidatas a hotspots."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from .geometry import load_image


@dataclass(frozen=True)
class ThermalConfig:
    # Faixas iniciais de vermelho HSV do OpenCV. Cada câmera/paleta deve
    # configurar seus próprios intervalos; vermelho cruza o limite H=0.
    hsv_ranges: tuple[tuple[tuple[int, int, int], tuple[int, int, int]], ...] = (
        ((0, 100, 100), (10, 255, 255)), ((170, 100, 100), (179, 255, 255)),
    )
    min_area: int = 20
    morph_kernel: int = 3
    morphology: bool = True

    def __post_init__(self) -> None:
        if self.min_area < 0 or self.morph_kernel < 1 or self.morph_kernel % 2 == 0:
            raise ValueError("Parâmetros térmicos inválidos")
        for lower, upper in self.hsv_ranges:
            if any(a < 0 or b > m or a > b for a, b, m in zip(lower, upper, (179, 255, 255))):
                raise ValueError("Faixa HSV inválida")


def analyze_thermal(path: str | Path | np.ndarray, output_dir: str | Path | None = None,
                    config: ThermalConfig | None = None,
                    include_artifacts: bool = False) -> dict[str, Any]:
    """Segmenta HSV de arquivo ou matriz BGR sem inferir temperatura em Celsius."""
    cfg = config or ThermalConfig()
    source = Path(path) if not isinstance(path, np.ndarray) else None
    image = load_image(source) if source is not None else path.copy()
    if image.size == 0:
        raise ValueError("Imagem de entrada vazia")
    if image.ndim != 3 or image.shape[2] < 3:
        raise ValueError("Imagem térmica deve conter pelo menos três canais BGR")
    bgr = image[:, :, :3].copy()
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    mask = np.zeros(image.shape[:2], dtype=np.uint8)
    for lower, upper in cfg.hsv_ranges:
        mask = cv2.bitwise_or(mask, cv2.inRange(hsv, np.array(lower, dtype=np.uint8), np.array(upper, dtype=np.uint8)))
    if cfg.morphology:
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (cfg.morph_kernel, cfg.morph_kernel))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(mask.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    regions = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < cfg.min_area:
            continue
        x, y, w, h = (int(v) for v in cv2.boundingRect(contour))
        regions.append({"area": area, "bbox": {"x": x, "y": y, "width": w, "height": h}})
    regions.sort(key=lambda r: (r["bbox"]["y"], r["bbox"]["x"]))
    annotated = bgr.copy()
    for region in regions:
        box = region["bbox"]
        cv2.rectangle(annotated, (box["x"], box["y"]), (box["x"] + box["width"], box["y"] + box["height"]), (0, 255, 0), 2)
    outputs: dict[str, str] = {}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, data in (("mascaras", mask), ("anotadas", annotated)):
            dest = out / f"{source.stem if source else 'imagem'}_{name}.png"
            if not cv2.imwrite(str(dest), data):
                raise OSError(f"Não foi possível salvar resultado: {dest}")
            outputs[name] = str(dest)
    h, w = image.shape[:2]
    result = {"path": str(source) if source else "<imagem em memória>", "width": int(w), "height": int(h),
            "channels": int(image.shape[2]), "region_count": len(regions),
            "regions": regions, "mask_fraction": float(np.count_nonzero(mask) / mask.size),
            "parameters": asdict(cfg), "outputs": outputs,
            "temperature_measurement": None,
            "interpretation": "Análise visual qualitativa; cores não representam temperatura calibrada em °C.",
            "warnings": [], "errors": []}
    if include_artifacts:
        result["artifacts"] = {"mask": mask, "annotated": annotated}
    return result


def classify_thermal_against_references(image: np.ndarray, normal_reference: np.ndarray,
                                        overheated_reference: np.ndarray,
                                        min_fraction_margin: float = 0.15) -> dict[str, Any]:
    """Classifica visualmente pela fração de cores quentes relativa às referências.

    A faixa é calibrada para as duas imagens de demonstração da AeroMotion.
    Não representa temperatura física e não deve ser generalizada para outra
    câmera, paleta térmica ou região de interesse sem nova validação.
    """
    if not 0 <= min_fraction_margin <= 1:
        raise ValueError("min_fraction_margin deve estar entre 0 e 1")
    warm_range = (((0, 80, 80), (35, 255, 255)),)

    def warm_fraction(source: np.ndarray) -> float:
        if source is None or source.size == 0 or source.ndim != 3 or source.shape[2] < 3:
            raise ValueError("Imagem térmica inválida para comparação")
        hsv = cv2.cvtColor(source[:, :, :3], cv2.COLOR_BGR2HSV)
        foreground = hsv[:, :, 2] > 25
        denom = int(np.count_nonzero(foreground))
        if denom == 0:
            raise ValueError("Imagem sem pixels visíveis para comparação térmica")
        warm = cv2.inRange(hsv, np.array(warm_range[0][0], np.uint8), np.array(warm_range[0][1], np.uint8)) > 0
        return float(np.count_nonzero(warm & foreground) / denom)

    fractions = {"warm_fraction": warm_fraction(image),
                 "normal_reference_warm_fraction": warm_fraction(normal_reference),
                 "overheated_reference_warm_fraction": warm_fraction(overheated_reference)}
    distances = {"normal": abs(fractions["warm_fraction"] - fractions["normal_reference_warm_fraction"]),
                 "overheated": abs(fractions["warm_fraction"] - fractions["overheated_reference_warm_fraction"])}
    ordered = sorted(distances.items(), key=lambda pair: pair[1])
    margin = ordered[1][1] - ordered[0][1]
    classification = "INCONCLUSIVA"
    if margin >= min_fraction_margin:
        classification = "TEMPERATURA NORMAL" if ordered[0][0] == "normal" else "SUPERAQUECIMENTO"
    return {"modality": "termica", "classification": classification,
            "metrics": {**fractions, "reference_distance_margin": float(margin)},
            "criteria": {"hsv_warm_range_opencv": {"lower": [0, 80, 80], "upper": [35, 255, 255]},
                         "foreground_value_minimum": 25, "minimum_reference_distance_margin": min_fraction_margin},
            "justification": ("A proporção de cores quentes se aproxima mais da referência normal." if classification == "TEMPERATURA NORMAL"
                              else "A proporção de cores quentes se aproxima mais da referência de superaquecimento." if classification == "SUPERAQUECIMENTO"
                              else "A proporção de cores quentes não distingue as referências com margem suficiente."),
            "limitations": ["Comparação visual qualitativa para a paleta das referências; não mede °C e não é universal para outras câmeras."]}
