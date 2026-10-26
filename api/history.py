"""Persistência SQLite do histórico de leituras e previsões.

O esquema original (timestamp, equipment_id, reading_json, result_json,
predicted_class, anomaly, inference_ms) é preservado.  A migração adiciona
colunas para tornar explícitos o regime operacional, a origem da leitura
(simulada/real) e as probabilidades por classe, sem apagar registros.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any


class PredictionHistory:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connect(self):
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equipment_id TEXT NOT NULL,
                    reading_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    predicted_class INTEGER NOT NULL,
                    anomaly INTEGER,
                    inference_ms REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    regime_operacional TEXT,
                    origem_leitura TEXT NOT NULL DEFAULT 'simulada',
                    probabilities_json TEXT,
                    regime_previous TEXT,
                    regime_changed_at TEXT,
                    perfil_sintetico TEXT,
                    perfil_anomalia TEXT
                )"""
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_predictions_equipment_time "
                "ON predictions(equipment_id, timestamp DESC)"
            )
            self._migrate(connection)
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_predictions_regime "
                "ON predictions(regime_operacional)"
            )

    def _migrate(self, connection: sqlite3.Connection) -> None:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(predictions)")
        }
        additions = {
            "regime_operacional": "TEXT",
            "origem_leitura": "TEXT NOT NULL DEFAULT 'simulada'",
            "probabilities_json": "TEXT",
            "regime_previous": "TEXT",
            "regime_changed_at": "TEXT",
            "perfil_sintetico": "TEXT",
            "perfil_anomalia": "TEXT",
        }
        for name, declaration in additions.items():
            if name not in columns:
                connection.execute(
                    f"ALTER TABLE predictions ADD COLUMN {name} {declaration}"
                )

        # Enriquecimento compatível das linhas antigas: o regime já existia no
        # reading_json/result_json (modo_operacao) e as probabilidades já
        # existiam no result_json.  Nada é apagado ou sobrescrito.
        rows = connection.execute(
            "SELECT id, reading_json, result_json FROM predictions "
            "WHERE regime_operacional IS NULL OR regime_operacional = '' "
            "OR probabilities_json IS NULL"
        ).fetchall()
        updates: list[tuple[Any, ...]] = []
        for row in rows:
            try:
                reading = json.loads(row["reading_json"])
                result = json.loads(row["result_json"])
            except (TypeError, json.JSONDecodeError):
                continue
            regime = (
                reading.get("regime_operacional")
                or reading.get("modo_operacao")
                or result.get("regime_operacional")
                or result.get("modo_operacao")
            )
            origin = (
                reading.get("origem_leitura")
                or result.get("origem_leitura")
                or "simulada"  # todo o histórico anterior foi gerado pelo simulador
            )
            probabilities = result.get("probabilidades")
            changed_at = (
                reading.get("regime_alterado_em")
                or result.get("regime_alterado_em")
            )
            previous = (
                reading.get("regime_anterior") or result.get("regime_anterior")
            )
            perfil_sintetico = (
                reading.get("perfil_sintetico") or result.get("perfil_sintetico")
            )
            perfil_anomalia = (
                reading.get("perfil_anomalia") or result.get("perfil_anomalia")
            )
            updates.append(
                (
                    regime,
                    origin,
                    json.dumps(probabilities, ensure_ascii=False)
                    if probabilities is not None
                    else None,
                    previous,
                    changed_at,
                    perfil_sintetico,
                    perfil_anomalia,
                    row["id"],
                )
            )
        if updates:
            connection.executemany(
                """UPDATE predictions
                SET regime_operacional = ?, origem_leitura = ?,
                    probabilities_json = ?, regime_previous = ?, regime_changed_at = ?,
                    perfil_sintetico = ?, perfil_anomalia = ?
                WHERE id = ?""",
                updates,
            )

    def add(self, reading: dict[str, Any], result: dict[str, Any]) -> None:
        probabilities = result.get("probabilidades")
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO predictions
                (timestamp, equipment_id, reading_json, result_json, predicted_class,
                 anomaly, inference_ms, regime_operacional, origem_leitura,
                 probabilities_json, regime_previous, regime_changed_at,
                 perfil_sintetico, perfil_anomalia)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    result["timestamp"], result["id_equipamento"],
                    json.dumps(reading, ensure_ascii=False, default=str),
                    json.dumps(result, ensure_ascii=False, default=str),
                    result["classe_prevista"],
                    None if result["anomalia"] is None else int(result["anomalia"]),
                    result["tempo_inferencia_ms"],
                    result.get("regime_operacional") or reading.get("modo_operacao"),
                    result.get("origem_leitura") or reading.get("origem_leitura") or "desconhecida",
                    json.dumps(probabilities, ensure_ascii=False)
                    if probabilities is not None
                    else None,
                    result.get("regime_anterior"),
                    result.get("regime_alterado_em"),
                    result.get("perfil_sintetico")
                    or reading.get("perfil_sintetico"),
                    result.get("perfil_anomalia")
                    or reading.get("perfil_anomalia"),
                ),
            )

    def list(self, limit: int, equipment_id: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT result_json FROM predictions"
        parameters: list[Any] = []
        if equipment_id:
            query += " WHERE equipment_id = ?"
            parameters.append(equipment_id)
        query += " ORDER BY timestamp DESC, id DESC LIMIT ?"
        parameters.append(limit)
        with self._connect() as connection:
            return [json.loads(row["result_json"]) for row in connection.execute(query, parameters)]

    def recent_readings(self, equipment_id: str, since: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT reading_json FROM predictions WHERE equipment_id = ? AND timestamp >= ? ORDER BY timestamp",
                (equipment_id, since),
            )
            return [json.loads(row["reading_json"]) for row in rows]

    def stats(self) -> dict[str, Any]:
        regimes = ("Cruzeiro", "Carga_Media", "Carga_Alta")
        with self._connect() as connection:
            total = connection.execute("SELECT COUNT(*) FROM predictions").fetchone()[0]
            equipments = connection.execute("SELECT COUNT(DISTINCT equipment_id) FROM predictions").fetchone()[0]
            last = connection.execute("SELECT MAX(timestamp) FROM predictions").fetchone()[0]
            anomalies = connection.execute("SELECT COUNT(*) FROM predictions WHERE anomaly = 1").fetchone()[0]
            mean_inference = connection.execute(
                "SELECT AVG(inference_ms) FROM predictions"
            ).fetchone()[0]
            rows = connection.execute(
                "SELECT predicted_class, COUNT(*) AS quantity FROM predictions GROUP BY predicted_class"
            ).fetchall()
            regime_rows = connection.execute(
                "SELECT regime_operacional, COUNT(*) AS quantity FROM predictions "
                "GROUP BY regime_operacional"
            ).fetchall()
            origins = connection.execute(
                "SELECT origem_leitura, COUNT(*) AS quantity FROM predictions "
                "GROUP BY origem_leitura"
            ).fetchall()
            profile_rows = connection.execute(
                "SELECT regime_operacional, perfil_sintetico, COUNT(*) AS quantity "
                "FROM predictions GROUP BY regime_operacional, perfil_sintetico"
            ).fetchall()
            anomaly_profile_rows = connection.execute(
                "SELECT regime_operacional, perfil_anomalia, COUNT(*) AS quantity "
                "FROM predictions WHERE perfil_sintetico = 'anormal' "
                "GROUP BY regime_operacional, perfil_anomalia"
            ).fetchall()
            all_class_rows = connection.execute(
                "SELECT regime_operacional, predicted_class, COUNT(*) AS quantity "
                "FROM predictions GROUP BY regime_operacional, predicted_class"
            ).fetchall()
            profile_class_rows = connection.execute(
                "SELECT regime_operacional, predicted_class, COUNT(*) AS quantity "
                "FROM predictions "
                "WHERE perfil_sintetico IN ('nominal', 'anormal') "
                "GROUP BY regime_operacional, predicted_class"
            ).fetchall()
            all_inference_rows = connection.execute(
                "SELECT regime_operacional, COUNT(*) AS quantity, AVG(inference_ms) AS mean_ms "
                "FROM predictions GROUP BY regime_operacional"
            ).fetchall()
            profile_inference_rows = connection.execute(
                "SELECT regime_operacional, COUNT(*) AS quantity, AVG(inference_ms) AS mean_ms "
                "FROM predictions "
                "WHERE perfil_sintetico IN ('nominal', 'anormal') "
                "GROUP BY regime_operacional"
            ).fetchall()
            all_probability_rows = connection.execute(
                "SELECT regime_operacional, probabilities_json FROM predictions "
                "WHERE probabilities_json IS NOT NULL"
            ).fetchall()
            profile_probability_rows = connection.execute(
                "SELECT regime_operacional, probabilities_json FROM predictions "
                "WHERE probabilities_json IS NOT NULL "
                "AND perfil_sintetico IN ('nominal', 'anormal')"
            ).fetchall()

        by_class = {str(row["predicted_class"]): row["quantity"] for row in rows}
        failures = sum(count for label, count in by_class.items() if label != "0")

        evaluation: dict[str, dict[str, Any]] = {
            regime: {
                "leituras": 0,
                "leituras_com_perfil": 0,
                "nominais": 0,
                "anormais": 0,
                "leituras_sem_perfil": 0,
                "proporcao_nominal_gerada": None,
                "proporcao_anormal_gerada": None,
                "classes_previstas": {},
                "classes_previstas_todas": {},
                "probabilidade_media_por_classe": {},
                "probabilidade_media_por_classe_todas": {},
                "perfis_anomalia": {},
                "tempo_medio_inferencia_ms": None,
                "tempo_medio_inferencia_todas_ms": None,
            }
            for regime in regimes
        }

        def bucket(name: str | None) -> dict[str, Any]:
            key = name if name in evaluation else "desconhecido"
            if key not in evaluation:
                evaluation[key] = {
                    "leituras": 0,
                    "leituras_com_perfil": 0,
                    "nominais": 0,
                    "anormais": 0,
                    "leituras_sem_perfil": 0,
                    "proporcao_nominal_gerada": None,
                    "proporcao_anormal_gerada": None,
                    "classes_previstas": {},
                    "classes_previstas_todas": {},
                    "probabilidade_media_por_classe": {},
                    "probabilidade_media_por_classe_todas": {},
                    "perfis_anomalia": {},
                    "tempo_medio_inferencia_ms": None,
                    "tempo_medio_inferencia_todas_ms": None,
                }
            return evaluation[key]

        for row in regime_rows:
            bucket(row["regime_operacional"])["leituras"] = row["quantity"]
        for row in profile_rows:
            item = bucket(row["regime_operacional"])
            if row["perfil_sintetico"] == "nominal":
                item["nominais"] += row["quantity"]
            elif row["perfil_sintetico"] == "anormal":
                item["anormais"] += row["quantity"]
            else:
                item["leituras_sem_perfil"] += row["quantity"]
        for row in anomaly_profile_rows:
            item = bucket(row["regime_operacional"])
            key = row["perfil_anomalia"] or "desconhecido"
            item["perfis_anomalia"][key] = row["quantity"]
        for row in profile_class_rows:
            item = bucket(row["regime_operacional"])
            item["classes_previstas"][str(row["predicted_class"])] = row["quantity"]
        for row in all_class_rows:
            item = bucket(row["regime_operacional"])
            item["classes_previstas_todas"][str(row["predicted_class"])] = row["quantity"]
        for row in profile_inference_rows:
            bucket(row["regime_operacional"])["tempo_medio_inferencia_ms"] = (
                round(float(row["mean_ms"]), 2) if row["mean_ms"] is not None else None
            )
        for row in all_inference_rows:
            bucket(row["regime_operacional"])["tempo_medio_inferencia_todas_ms"] = (
                round(float(row["mean_ms"]), 2) if row["mean_ms"] is not None else None
            )

        def average_probabilities(
            rows: list[sqlite3.Row],
        ) -> dict[str, dict[str, float]]:
            sums: dict[str, dict[str, float]] = {}
            counts: dict[str, dict[str, int]] = {}
            for row in rows:
                key = (
                    row["regime_operacional"]
                    if row["regime_operacional"] in evaluation
                    else "desconhecido"
                )
                bucket(key)
                try:
                    probabilities = json.loads(row["probabilities_json"])
                except (TypeError, json.JSONDecodeError):
                    continue
                if not isinstance(probabilities, dict):
                    continue
                for label, value in probabilities.items():
                    try:
                        numeric = float(value)
                    except (TypeError, ValueError):
                        continue
                    label = str(label)
                    sums.setdefault(key, {})[label] = (
                        sums.setdefault(key, {}).get(label, 0.0) + numeric
                    )
                    counts.setdefault(key, {})[label] = (
                        counts.setdefault(key, {}).get(label, 0) + 1
                    )
            return {
                regime: {
                    label: round(sums[regime][label] / count, 4)
                    for label, count in label_counts.items()
                    if count
                }
                for regime, label_counts in counts.items()
            }

        profile_probabilities = average_probabilities(profile_probability_rows)
        all_probabilities = average_probabilities(all_probability_rows)

        for regime, item in evaluation.items():
            item["leituras_com_perfil"] = item["nominais"] + item["anormais"]
            known = item["leituras_com_perfil"]
            if known:
                item["proporcao_nominal_gerada"] = round(item["nominais"] / known, 4)
                item["proporcao_anormal_gerada"] = round(item["anormais"] / known, 4)
            item["probabilidade_media_por_classe"] = profile_probabilities.get(
                regime, {}
            )
            item["probabilidade_media_por_classe_todas"] = all_probabilities.get(
                regime, {}
            )

        return {
            "leituras_processadas": total,
            "equipamentos_monitorados": equipments,
            "predicoes_por_classe": by_class,
            "predicoes_por_regime": {
                row["regime_operacional"] or "desconhecido": row["quantity"]
                for row in regime_rows
            },
            "predicoes_por_origem": {
                row["origem_leitura"] or "desconhecida": row["quantity"]
                for row in origins
            },
            "predicoes_falha": failures,
            "proporcao_predicoes_falha": failures / total if total else 0.0,
            "anomalias_detectadas": anomalies,
            "tempo_medio_inferencia_ms": (
                round(float(mean_inference), 2) if mean_inference is not None else None
            ),
            "avaliacao_por_regime": evaluation,
            "ultima_leitura": last,
            "aviso": (
                "As proporções nominais/anormais referem-se ao gerador sintético e "
                "são diferentes da distribuição de classes previstas pelo modelo. "
                "Classes, probabilidades e tempo médio da avaliação usam apenas o "
                "coorte com perfil; as chaves *_todas refletem todo o histórico do "
                "regime. Valores representam previsões e anomalias da simulação; não "
                "confirmam falhas físicas."
            ),
        }
