"""Ferramentas reutilizáveis para inspeção geométrica com OpenCV."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass(frozen=True)
class GeometryConfig:
    gaussian_kernel: int = 5
    canny_low: int = 50
    canny_high: int = 150
    min_contour_area: float = 20.0

    def __post_init__(self) -> None:
        if self.gaussian_kernel < 1 or self.gaussian_kernel % 2 == 0:
            raise ValueError("gaussian_kernel deve ser positivo e ímpar")
        if not 0 <= self.canny_low < self.canny_high <= 255:
            raise ValueError("Limiares Canny inválidos")
        if self.min_contour_area < 0:
            raise ValueError("min_contour_area não pode ser negativo")


def load_image(path: str | Path) -> np.ndarray:
    """Carrega imagem preservando o arquivo e lança erro claro se inválido."""
    image = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if image is None:
        raise ValueError(f"Imagem inexistente, corrompida ou não suportada: {path}")
    if image.ndim not in (2, 3):
        raise ValueError(f"Formato de imagem inválido: {path}")
    return image


def contour_features(contour: np.ndarray, index: int = 0) -> dict[str, Any]:
    """Calcula atributos de um contorno; circularidade ideal aproxima-se de 1.

    O valor observado também depende da discretização, segmentação e contorno
    encontrado, portanto não deve ser usado isoladamente para declarar defeito.
    """
    area = float(cv2.contourArea(contour))
    perimeter = float(cv2.arcLength(contour, True))
    circularity = float(4.0 * np.pi * area / perimeter**2) if perimeter > 0 and np.isfinite(perimeter) else None
    x, y, width, height = (int(v) for v in cv2.boundingRect(contour))
    moments = cv2.moments(contour)
    centroid = None
    if moments["m00"] != 0 and np.isfinite(moments["m00"]):
        centroid = {"x": float(moments["m10"] / moments["m00"]), "y": float(moments["m01"] / moments["m00"])}
    result = {
        "index": index, "area": area, "perimeter": perimeter,
        "circularity": circularity, "bbox": {"x": x, "y": y, "width": width, "height": height},
        "centroid": centroid, "aspect_ratio": float(width / height) if height else None,
    }
    return result


def analyze_geometry(path: str | Path | np.ndarray, output_dir: str | Path | None = None,
                     config: GeometryConfig | None = None,
                     include_artifacts: bool = False) -> dict[str, Any]:
    """Executa cinza, blur, Canny e contornos; aceita matriz BGR sem gravá-la."""
    cfg = config or GeometryConfig()
    source = Path(path) if not isinstance(path, np.ndarray) else None
    image = load_image(source) if source is not None else path.copy()
    if image.size == 0 or image.ndim not in (2, 3):
        raise ValueError("Imagem de entrada vazia ou inválida")
    gray = image if image.ndim == 2 else cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (cfg.gaussian_kernel, cfg.gaussian_kernel), 0)
    edges = cv2.Canny(blurred, cfg.canny_low, cfg.canny_high)
    found, _ = cv2.findContours(edges.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    relevant = [c for c in found if cv2.contourArea(c) >= cfg.min_contour_area]
    features = [contour_features(c, i) for i, c in enumerate(relevant)]
    contoured = cv2.cvtColor(image, cv2.COLOR_GRAY2BGR) if image.ndim == 2 else image[:, :, :3].copy()
    cv2.drawContours(contoured, relevant, -1, (0, 255, 0), 2)
    annotated = contoured.copy()
    for f in features:
        b = f["bbox"]
        cv2.rectangle(annotated, (b["x"], b["y"]), (b["x"] + b["width"], b["y"] + b["height"]), (0, 0, 255), 1)
    outputs: dict[str, str] = {}
    if output_dir is not None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        for name, data in (("cinza", gray), ("bordas", edges), ("anotadas", annotated)):
            dest = out / f"{source.stem if source else 'imagem'}_{name}.png"
            if not cv2.imwrite(str(dest), data):
                raise OSError(f"Não foi possível salvar resultado: {dest}")
            outputs[name] = str(dest)
    height, width = image.shape[:2]
    result = {
        "path": str(source) if source else "<imagem em memória>", "width": int(width), "height": int(height),
        "channels": int(1 if image.ndim == 2 else image.shape[2]),
        "depth": str(image.dtype), "contour_count": len(features),
        "contours": features, "parameters": asdict(cfg), "outputs": outputs,
        "warnings": [], "errors": [],
    }
    if include_artifacts:
        result["artifacts"] = {"gray": gray, "edges": edges, "contours": contoured, "annotated": annotated}
    return result


def compare_geometry(reference: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    """Compara listas de atributos compatíveis; diferenças são apenas indicativas."""
    if (reference.get("width"), reference.get("height")) != (candidate.get("width"), candidate.get("height")):
        return {"comparable": False, "warning": "Dimensões diferentes; alinhamento/escala não verificados."}
    def summary(result: dict[str, Any]) -> dict[str, float | None]:
        contours = result.get("contours", [])
        return {key: (float(np.mean([c[key] for c in contours if c.get(key) is not None])) if any(c.get(key) is not None for c in contours) else None)
                for key in ("area", "aspect_ratio", "circularity")}
    a, b = summary(reference), summary(candidate)
    return {"comparable": True, "reference": a, "candidate": b,
            "delta": {k: (None if a[k] is None or b[k] is None else b[k] - a[k]) for k in a},
            "warning": "Diferenças podem refletir enquadramento, perspectiva, escala ou iluminação; não são diagnóstico de defeito."}


def _normalized_silhouette(image: np.ndarray, size: tuple[int, int] = (512, 256)) -> np.ndarray:
    """Extrai e normaliza a maior silhueta, preservando proporção e centralizando."""
    if image is None or image.size == 0 or image.ndim not in (2, 3):
        raise ValueError("Imagem inválida para comparação geométrica")
    gray = image if image.ndim == 2 else cv2.cvtColor(image[:, :, :3], cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    _, mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = [c for c in contours if cv2.contourArea(c) >= 100]
    if not contours:
        raise ValueError("Não foi possível segmentar uma silhueta relevante")
    contour = max(contours, key=cv2.contourArea)
    x, y, w, h = cv2.boundingRect(contour)
    crop = np.zeros((h, w), np.uint8)
    shifted = contour.copy()
    shifted[:, 0, 0] -= x
    shifted[:, 0, 1] -= y
    cv2.drawContours(crop, [shifted], -1, 255, thickness=cv2.FILLED)
    target_w, target_h = size
    scale = min((target_w - 8) / w, (target_h - 8) / h)
    resized = cv2.resize(crop, (max(1, round(w * scale)), max(1, round(h * scale))), interpolation=cv2.INTER_NEAREST)
    canvas = np.zeros((target_h, target_w), np.uint8)
    xx, yy = (target_w - resized.shape[1]) // 2, (target_h - resized.shape[0]) // 2
    canvas[yy:yy + resized.shape[0], xx:xx + resized.shape[1]] = resized
    return canvas


def classify_geometry_against_references(image: np.ndarray, normal_reference: np.ndarray,
                                         defective_reference: np.ndarray,
                                         min_iou: float = 0.95, min_margin: float = 0.05) -> dict[str, Any]:
    """Compara silhuetas normalizadas; sem correspondência forte, retorna inconclusiva.

    Esse critério serve para demonstração com referências compatíveis, não para
    tolerâncias industriais nem para componentes com geometrias distintas.
    """
    if not 0 <= min_iou <= 1 or not 0 <= min_margin <= 1:
        raise ValueError("Limiares IoU devem estar entre 0 e 1")
    candidate = _normalized_silhouette(image)
    normal = _normalized_silhouette(normal_reference)
    defective = _normalized_silhouette(defective_reference)

    def iou(a: np.ndarray, b: np.ndarray) -> float:
        aa, bb = a > 0, b > 0
        union = np.count_nonzero(aa | bb)
        return float(np.count_nonzero(aa & bb) / union) if union else 0.0

    scores = {"normal_reference_iou": iou(candidate, normal),
              "defective_reference_iou": iou(candidate, defective)}
    ordered = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
    margin = ordered[0][1] - ordered[1][1]
    classification = "INCONCLUSIVA"
    if ordered[0][1] >= min_iou and margin >= min_margin:
        classification = "DENTRO DOS CONFORMES" if ordered[0][0].startswith("normal") else "REPROVADA"
    return {"modality": "geometrica", "classification": classification, "metrics": {**scores, "match_margin": margin},
            "criteria": {"minimum_reference_iou": min_iou, "minimum_match_margin": min_margin,
                         "normalization": "maior silhueta preenchida, escala preservada e centralização"},
            "justification": ("A silhueta corresponde de forma clara à referência normal." if classification == "DENTRO DOS CONFORMES"
                              else "A silhueta corresponde de forma clara à referência deformada." if classification == "REPROVADA"
                              else "A silhueta não corresponde com margem suficiente a nenhuma referência."),
            "limitations": ["Comparação demonstrativa para a mesma peça e enquadramento semelhante; não equivale a inspeção certificada."]}
