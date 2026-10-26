"""Carregamento dos artefatos e composição de features temporais."""
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from time import perf_counter
from typing import Any

import joblib
import numpy as np
import pandas as pd

from api.history import PredictionHistory

CLASS_NAMES = {
    0: "Normal",
    1: "Desgaste_Rolamento",
    2: "Desbalanceamento_Rotor",
    3: "Cavitacao_Superaquecimento",
}
FEATURES = [
    "modo_operacao", "horas_operacao_acumuladas", "temperatura_mancal_c",
    "vibracao_rms_mms", "pressao_oleo_bar", "rotacao_rpm", "emissao_acustica_db",
    "corrente_eletrica_amp", "temperatura_mancal_c_media_1h", "temperatura_mancal_c_std_1h",
    "temperatura_mancal_c_media_6h", "temperatura_mancal_c_std_6h",
    "vibracao_rms_mms_media_1h", "vibracao_rms_mms_std_1h",
    "vibracao_rms_mms_media_6h", "vibracao_rms_mms_std_6h", "severidade_dinamica",
]
# Campos operacionais que não são sensores e não devem entrar no dicionário
# de telemetria devolvido ao dashboard.
METADATA_FIELDS = {
    "timestamp", "id_equipamento", "modo_operacao", "cenario_simulado",
    "regime_operacional", "regime_anterior", "regime_alterado_em", "origem_leitura",
    "perfil_sintetico", "perfil_anomalia",
}
SENSOR_LIMITS = {
    "temperatura_mancal_c": (45, 85), "vibracao_rms_mms": (1, 4.5),
    "pressao_oleo_bar": (3.5, 5.2), "rotacao_rpm": (2300, 3600),
    "emissao_acustica_db": (40, 68), "corrente_eletrica_amp": (18, 42),
}


class ModelService:
    def __init__(self, root_dir: Path, history: PredictionHistory) -> None:
        models_dir = root_dir / "data" / "processed" / "modelos"
        self.classifier_path = models_dir / "random_forest.joblib"
        self.anomaly_path = models_dir / "isolation_forest.joblib"
        self.anomaly_preprocessor_path = models_dir / "preprocessador_anomalias.joblib"
        if not self.classifier_path.exists():
            raise FileNotFoundError(f"Classificador não encontrado: {self.classifier_path}")
        self.classifier = joblib.load(self.classifier_path)
        self.anomaly_model = None
        self.anomaly_preprocessor = None
        if self.anomaly_path.exists() and self.anomaly_preprocessor_path.exists():
            self.anomaly_model = joblib.load(self.anomaly_path)
            self.anomaly_preprocessor = joblib.load(self.anomaly_preprocessor_path)
        self.history = history
        self.buffers: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self._restore_buffers()

        expected = list(getattr(self.classifier, "feature_names_in_", []))
        if expected and expected != FEATURES:
            raise ValueError("As features do classificador não correspondem ao contrato auditado.")

    def _restore_buffers(self) -> None:
        now = datetime.now()
        since = (now - timedelta(hours=6)).isoformat(sep=" ")
        for equipment in ("TURB-101", "TURB-102", "TURB-103", "TURB-104"):
            for reading in self.history.recent_readings(equipment, since):
                reading["timestamp"] = datetime.fromisoformat(reading["timestamp"])
                self.buffers[equipment].append(reading)

    @staticmethod
    def _rolling(rows: list[dict[str, Any]], field: str, timestamp: datetime, window: timedelta) -> tuple[float, float]:
        values = [row[field] for row in rows if row["timestamp"] > timestamp - window and row["timestamp"] <= timestamp]
        if not values:
            return np.nan, np.nan
        return float(np.mean(values)), float(np.std(values, ddof=1)) if len(values) > 1 else np.nan

    def _features(self, reading: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        equipment = reading["id_equipamento"]
        timestamp = reading["timestamp"]
        buffer = self.buffers[equipment]
        if buffer and timestamp <= buffer[-1]["timestamp"]:
            raise ValueError("O timestamp deve ser posterior à última leitura do equipamento para preservar a ordem temporal.")
        rows = list(buffer) + [reading]
        feature_row = dict(reading)
        for field in ("temperatura_mancal_c", "vibracao_rms_mms"):
            for label, window in (("1h", timedelta(hours=1)), ("6h", timedelta(hours=6))):
                mean, std = self._rolling(rows, field, timestamp, window)
                feature_row[f"{field}_media_{label}"] = mean
                feature_row[f"{field}_std_{label}"] = std
        feature_row["severidade_dinamica"] = reading["vibracao_rms_mms"] / reading["rotacao_rpm"]
        warmup = len([row for row in rows if row["timestamp"] > timestamp - timedelta(hours=1)]) < 2
        buffer.append(reading)
        while buffer and buffer[0]["timestamp"] <= timestamp - timedelta(hours=6):
            buffer.popleft()
        return feature_row, warmup

    def predict(self, reading: dict[str, Any]) -> dict[str, Any]:
        started = perf_counter()
        feature_row, warmup = self._features(reading)
        frame = pd.DataFrame([{name: feature_row[name] for name in FEATURES}], columns=FEATURES)
        predicted = int(self.classifier.predict(frame)[0])
        probabilities = None
        if hasattr(self.classifier, "predict_proba"):
            probabilities = {
                str(int(label)): float(value)
                for label, value in zip(self.classifier.classes_, self.classifier.predict_proba(frame)[0])
            }
        anomaly = None
        if self.anomaly_model is not None and self.anomaly_preprocessor is not None:
            transformed = self.anomaly_preprocessor.transform(frame)
            anomaly = bool(self.anomaly_model.predict(transformed)[0] == -1)
        conditions = {
            sensor: "fora_da_faixa" if not low <= reading[sensor] <= high else "normal"
            for sensor, (low, high) in SENSOR_LIMITS.items()
        }
        result = {
            "timestamp": reading["timestamp"].isoformat(sep=" "),
            "id_equipamento": reading["id_equipamento"],
            "cenario_simulado": reading.get("cenario_simulado"),
            "classe_prevista": predicted,
            "nome_classe_prevista": CLASS_NAMES[predicted],
            "classe_maior_probabilidade": predicted,
            "probabilidades": probabilities,
            "anomalia": anomaly,
            "aquecimento_historico": warmup,
            "sensores": {key: reading[key] for key in reading if key not in METADATA_FIELDS},
            "modo_operacao": reading["modo_operacao"],
            "regime_operacional": reading.get("regime_operacional") or reading["modo_operacao"],
            "regime_anterior": reading.get("regime_anterior"),
            "regime_alterado_em": (
                reading["regime_alterado_em"].isoformat(sep=" ")
                if isinstance(reading.get("regime_alterado_em"), datetime)
                else reading.get("regime_alterado_em")
            ),
            "origem_leitura": reading.get("origem_leitura") or "desconhecida",
            "perfil_sintetico": reading.get("perfil_sintetico"),
            "perfil_anomalia": reading.get("perfil_anomalia"),
            "tipo_falha_predita": CLASS_NAMES[predicted],
            "indicadores_condicao": conditions,
            "tempo_inferencia_ms": round((perf_counter() - started) * 1000, 2),
        }
        self.history.add(reading, result)
        return result

    @property
    def status(self) -> dict[str, Any]:
        return {
            "classificador": self.classifier_path.name,
            "classificador_disponivel": self.classifier is not None,
            "detector_anomalias_disponivel": self.anomaly_model is not None,
            "features": FEATURES,
        }
