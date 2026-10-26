"""Testes do simulador, dinâmica temporal, controle e migração do histórico."""
from __future__ import annotations

import json
import math
import sqlite3
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import pandas as pd

import simulator as sim
from api.history import PredictionHistory
from api import predictor
from frontend import charts


class RegimeProfileTests(unittest.TestCase):
    def test_default_regime_is_cruise(self) -> None:
        self.assertEqual(sim.DEFAULT_REGIME, "Cruzeiro")
        self.assertEqual(sim.TelemetrySimulator(seed=1).regime, "Cruzeiro")

    def test_profiles_are_ordered_and_within_operating_limits(self) -> None:
        order = ["Cruzeiro", "Carga_Media", "Carga_Alta"]
        for field in sim.SENSOR_FIELDS:
            values = [sim.REGIME_PROFILES[name][field] for name in order]
            self.assertEqual(values, sorted(values), f"{field} deve crescer com a carga")
            low, high = sim.SENSOR_LIMITS[field]
            for value in values:
                self.assertGreaterEqual(value, low, f"{field} abaixo do limite")
                self.assertLessEqual(value, high, f"{field} acima do limite")

    def test_only_three_regimes_exist(self) -> None:
        self.assertEqual(sim.REGIMES, ("Cruzeiro", "Carga_Media", "Carga_Alta"))
        self.assertEqual(set(sim.REGIME_LABELS), set(sim.REGIMES))

    def test_central_regime_config_has_exact_required_ratios(self) -> None:
        expected = {
            "Cruzeiro": (0.95, 0.05),
            "Carga_Media": (0.70, 0.30),
            "Carga_Alta": (0.40, 0.60),
        }
        for regime, (nominal, anomaly) in expected.items():
            config = sim.REGIME_CONFIG[regime]
            self.assertAlmostEqual(config["nominal_ratio"], nominal)
            self.assertAlmostEqual(config["anomaly_ratio"], anomaly)
            self.assertAlmostEqual(
                config["nominal_ratio"] + config["anomaly_ratio"], 1.0
            )
            block_size = int(config["block_size"])
            count = int(round(config["nominal_ratio"] * block_size))
            self.assertAlmostEqual(count / block_size, config["nominal_ratio"])
            self.assertAlmostEqual(sum(config["anomaly_weights"].values()), 1.0)

    def test_anomaly_profile_targets_follow_physical_profiles(self) -> None:
        thermal = sim.anomaly_offset_targets("Carga_Alta", "A")
        mechanical = sim.anomaly_offset_targets("Carga_Alta", "B")
        combined = sim.anomaly_offset_targets("Carga_Alta", "C")
        nominal = sim.anomaly_offset_targets("Carga_Alta", None)

        self.assertTrue(all(value == 0.0 for value in nominal.values()))
        self.assertGreater(thermal["temperatura_mancal_c"], 0.0)
        self.assertLess(thermal["pressao_oleo_bar"], 0.0)
        self.assertEqual(thermal["vibracao_rms_mms"], 0.0)
        self.assertGreater(mechanical["vibracao_rms_mms"], 0.0)
        self.assertGreater(mechanical["emissao_acustica_db"], 0.0)
        self.assertGreater(combined["vibracao_rms_mms"], 0.0)
        self.assertGreater(combined["corrente_eletrica_amp"], 0.0)
        self.assertGreater(combined["temperatura_mancal_c"], 0.0)


class TemporalDynamicsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.sim = sim.TelemetrySimulator(seed=7)

    def _state(self) -> sim.EquipmentState:
        return self.sim.states["TURB-101"]

    def test_temperature_rises_gradually(self) -> None:
        initial = self._state().temperature
        self.sim.set_regime("Carga_Alta")
        first = self.sim.step(5.0)[0]["temperatura_mancal_c"]
        # Após 5 s a temperatura não pode saltar para o alvo (72 °C).
        self.assertLess(first - initial, 3.0)
        self.assertGreater(first, initial)

        for _ in range(60):  # 300 s
            self.sim.step(5.0)
        heated = self._state().temperature
        self.assertGreater(heated, initial + 8.0)
        self.assertLess(heated, sim.REGIME_PROFILES["Carga_Alta"]["temperatura_mancal_c"])

    def test_vibration_responds_faster_than_temperature(self) -> None:
        base_temp = self._state().temperature
        base_vib = self._state().vibration
        self.sim.set_regime("Carga_Alta")
        for _ in range(4):  # 20 s
            self.sim.step(5.0)

        target_temp = sim.REGIME_PROFILES["Carga_Alta"]["temperatura_mancal_c"]
        target_vib = sim.REGIME_PROFILES["Carga_Alta"]["vibracao_rms_mms"]
        temp_fraction = (self._state().temperature - base_temp) / (target_temp - base_temp)
        vib_fraction = (self._state().vibration - base_vib) / (target_vib - base_vib)
        self.assertGreater(vib_fraction, temp_fraction)

    def test_switch_preserves_state_and_hours(self) -> None:
        state_id = id(self._state())
        for _ in range(3):
            self.sim.step(5.0)
        hours_before = self._state().hours
        temperature_before = self._state().temperature

        self.assertTrue(self.sim.set_regime("Carga_Media"))
        self.assertEqual(id(self._state()), state_id)
        self.assertGreaterEqual(self._state().hours, hours_before)
        self.assertAlmostEqual(self._state().temperature, temperature_before, places=6)
        self.assertFalse(self.sim.set_regime("Carga_Media"), "Regime repetido não deve gerar transição")
        self.assertEqual(self.sim.previous_regime, "Cruzeiro")

    def test_returning_from_high_load_cools_without_restart(self) -> None:
        self.sim.set_regime("Carga_Alta")
        for _ in range(80):
            self.sim.step(5.0)
        hot = self._state().temperature
        identity = id(self.sim)

        self.assertTrue(self.sim.set_regime("Cruzeiro"))
        for _ in range(40):
            self.sim.step(5.0)
        cooler = self._state().temperature

        self.assertLess(cooler, hot)
        self.assertEqual(id(self.sim), identity)
        self.assertEqual(self.sim.regime, "Cruzeiro")

    def test_high_load_base_state_stabilizes_at_nominal_profile(self) -> None:
        self.sim.set_regime("Carga_Alta")
        for _ in range(150):  # 750 s, mais de 8 constantes térmicas
            self.sim.step(5.0)
        state = self._state()
        target = sim.REGIME_PROFILES["Carga_Alta"]
        # O estado físico de base não inclui o offset do perfil de anomalia.
        # Ele deve convergir para o alvo nominal do regime.
        for field, attribute in {
            "temperatura_mancal_c": "temperature",
            "vibracao_rms_mms": "vibration",
            "pressao_oleo_bar": "pressure",
            "rotacao_rpm": "rotation",
            "emissao_acustica_db": "acoustic",
            "corrente_eletrica_amp": "current",
        }.items():
            value = getattr(state, attribute)
            low, high = sim.SENSOR_LIMITS[field]
            self.assertGreaterEqual(value, low)
            self.assertLessEqual(value, high)
        self.assertAlmostEqual(
            state.temperature, target["temperatura_mancal_c"], delta=2.0
        )
        self.assertAlmostEqual(
            state.vibration, target["vibracao_rms_mms"], delta=0.25
        )
        self.assertAlmostEqual(
            state.rotation, target["rotacao_rpm"], delta=15.0
        )

    def test_readings_use_real_sensors_and_never_a_predicted_class(self) -> None:
        reading = self.sim.step(5.0)[0]
        for field in sim.SENSOR_FIELDS:
            self.assertIn(field, reading)
            self.assertIsInstance(reading[field], float)
            low, high = sim.GENERATION_LIMITS[field]
            self.assertGreaterEqual(reading[field], low)
            self.assertLessEqual(reading[field], high)
        self.assertEqual(reading["regime_operacional"], "Cruzeiro")
        self.assertEqual(reading["origem_leitura"], "simulada")
        self.assertIn(reading["perfil_sintetico"], {"nominal", "anormal"})
        if reading["perfil_sintetico"] == "nominal":
            self.assertIsNone(reading["perfil_anomalia"])
        else:
            self.assertIn(reading["perfil_anomalia"], {"A", "B", "C"})
        for forbidden in ("classe_prevista", "nome_classe_prevista", "probabilidades"):
            self.assertNotIn(forbidden, reading)


class SyntheticGenerationTests(unittest.TestCase):
    """Verifica as proporções do gerador, não as classes previstas pelo modelo."""

    def _readings(
        self, regime: str, quantity: int = 100, seed: int = 123
    ) -> list[dict]:
        generator = sim.TelemetrySimulator(
            equipments=("TURB-101",), regime=regime, seed=seed
        )
        return [generator.step(5.0)[0] for _ in range(quantity)]

    def test_100_readings_match_each_configured_proportion(self) -> None:
        expected = {
            "Cruzeiro": (95, 5),
            "Carga_Media": (70, 30),
            "Carga_Alta": (40, 60),
        }
        for regime, (nominal, anomaly) in expected.items():
            with self.subTest(regime=regime):
                readings = self._readings(regime)
                counts = Counter(
                    reading["perfil_sintetico"] for reading in readings
                )
                self.assertEqual(counts["nominal"], nominal)
                self.assertEqual(counts["anormal"], anomaly)
                self.assertEqual(sum(counts.values()), 100)

    def test_each_configured_block_has_exact_counts_and_high_load_has_2_of_5(
        self,
    ) -> None:
        for regime in sim.REGIMES:
            with self.subTest(regime=regime):
                readings = self._readings(regime)
                block_size = int(sim.REGIME_CONFIG[regime]["block_size"])
                nominal_ratio = float(sim.REGIME_CONFIG[regime]["nominal_ratio"])
                expected_nominal = int(round(nominal_ratio * block_size))
                for start in range(0, 100, block_size):
                    block = readings[start : start + block_size]
                    counts = Counter(
                        reading["perfil_sintetico"] for reading in block
                    )
                    self.assertEqual(counts["nominal"], expected_nominal)
                    self.assertEqual(
                        counts["anormal"], block_size - expected_nominal
                    )

    def test_high_load_distributes_anomalies_across_physical_profiles(self) -> None:
        readings = self._readings("Carga_Alta")
        anomalies = [
            reading
            for reading in readings
            if reading["perfil_sintetico"] == "anormal"
        ]
        nominal = [
            reading
            for reading in readings
            if reading["perfil_sintetico"] == "nominal"
        ]
        self.assertEqual(len(anomalies), 60)
        profiles = Counter(reading["perfil_anomalia"] for reading in anomalies)
        self.assertEqual(set(profiles), {"A", "B", "C"})

        def mean(rows: list[dict], field: str) -> float:
            return sum(row[field] for row in rows) / len(rows)

        nominal_temp = mean(nominal, "temperatura_mancal_c")
        nominal_vibration = mean(nominal, "vibracao_rms_mms")
        nominal_current = mean(nominal, "corrente_eletrica_amp")
        nominal_pressure = mean(nominal, "pressao_oleo_bar")

        thermal = [row for row in anomalies if row["perfil_anomalia"] == "A"]
        mechanical = [row for row in anomalies if row["perfil_anomalia"] == "B"]
        combined = [row for row in anomalies if row["perfil_anomalia"] == "C"]

        self.assertGreater(mean(thermal, "temperatura_mancal_c"), nominal_temp + 2.0)
        self.assertLess(mean(thermal, "pressao_oleo_bar"), nominal_pressure - 0.3)
        self.assertGreater(
            mean(mechanical, "vibracao_rms_mms"), nominal_vibration + 1.0
        )
        self.assertGreater(
            mean(mechanical, "emissao_acustica_db"),
            mean(nominal, "emissao_acustica_db") + 5.0,
        )
        self.assertGreater(
            mean(combined, "corrente_eletrica_amp"), nominal_current + 5.0
        )

    def test_generated_values_are_finite_continuous_and_inside_generation_ranges(
        self,
    ) -> None:
        max_step = {
            "temperatura_mancal_c": 8.0,
            "vibracao_rms_mms": 5.0,
            "pressao_oleo_bar": 1.2,
            "rotacao_rpm": 80.0,
            "emissao_acustica_db": 14.0,
            "corrente_eletrica_amp": 12.0,
        }
        for regime in sim.REGIMES:
            with self.subTest(regime=regime):
                readings = self._readings(regime)
                for field in sim.SENSOR_FIELDS:
                    values = [reading[field] for reading in readings]
                    low, high = sim.GENERATION_LIMITS[field]
                    for value in values:
                        self.assertTrue(math.isfinite(value), f"{field} não finito")
                        self.assertGreaterEqual(value, low)
                        self.assertLessEqual(value, high)
                    changes = [
                        abs(current - previous)
                        for previous, current in zip(values, values[1:])
                    ]
                    self.assertLessEqual(
                        max(changes),
                        max_step[field],
                        f"salto excessivo em {field} no regime {regime}",
                    )

    def test_switch_during_execution_preserves_metadata_and_proportions(self) -> None:
        generator = sim.TelemetrySimulator(
            equipments=("TURB-101",), regime="Cruzeiro", seed=99
        )
        for _ in range(30):
            generator.step(5.0)
        self.assertTrue(generator.set_regime("Carga_Alta"))
        readings = [generator.step(5.0)[0] for _ in range(100)]
        self.assertTrue(
            all(reading["regime_operacional"] == "Carga_Alta" for reading in readings)
        )
        counts = Counter(reading["perfil_sintetico"] for reading in readings)
        self.assertEqual(counts["nominal"], 40)
        self.assertEqual(counts["anormal"], 60)

    def test_profile_is_generator_metadata_not_a_predicted_class(self) -> None:
        reading = self._readings("Carga_Alta", quantity=1)[0]
        for key in ("classe_prevista", "nome_classe_prevista", "probabilidades"):
            self.assertNotIn(key, reading)
        self.assertIn(reading["perfil_sintetico"], {"nominal", "anormal"})
        if reading["perfil_anomalia"] is not None:
            self.assertIn(reading["perfil_anomalia"], {"A", "B", "C"})

    def test_raw_reading_columns_are_compatible_with_the_model_pipeline(self) -> None:
        pipeline_path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "processed"
            / "modelos"
            / "random_forest.joblib"
        )
        pipeline = joblib.load(pipeline_path)
        self.assertEqual(list(pipeline.feature_names_in_), predictor.FEATURES)
        self.assertEqual(len(predictor.FEATURES), 17)
        self.assertTrue(set(sim.SENSOR_FIELDS).issubset(set(predictor.FEATURES)))
        self.assertFalse(
            {"perfil_sintetico", "perfil_anomalia"} & set(predictor.FEATURES)
        )
        self.assertIn("modo_operacao", predictor.FEATURES)
        self.assertTrue(
            {"perfil_sintetico", "perfil_anomalia"}.issubset(
                predictor.METADATA_FIELDS
            )
        )

        readings = self._readings("Carga_Alta")
        for reading in readings:
            sensor_payload = {
                key: value
                for key, value in reading.items()
                if key not in predictor.METADATA_FIELDS
            }
            self.assertTrue(set(sim.SENSOR_FIELDS).issubset(sensor_payload))
            self.assertNotIn("perfil_sintetico", sensor_payload)
            self.assertNotIn("perfil_anomalia", sensor_payload)


class ControlPlaneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.control = self.dir / "simulator_control.json"
        self.state = self.dir / "simulator_state.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_control_roundtrip_and_invalid_command(self) -> None:
        self.assertIsNone(sim.read_control(self.control))
        sim.write_control("Carga_Alta", path=self.control)
        stored = sim.read_control(self.control)
        self.assertEqual(stored["regime"], "Carga_Alta")
        self.assertEqual(stored["action"], "run")

        with self.assertRaises(ValueError):
            sim.write_control("Turbo_Maximo", path=self.control)
        with self.assertRaises(ValueError):
            sim.write_control("Cruzeiro", action="explode", path=self.control)

    def test_status_offline_then_online_from_heartbeat(self) -> None:
        sim.write_control("Carga_Media", path=self.control)
        offline = sim.simulator_status(control_path=self.control, state_path=self.state)
        self.assertFalse(offline["simulador_online"])
        self.assertEqual(offline["regime_selecionado"], "Carga_Media")

        changed = datetime.now() - timedelta(seconds=30)
        sim.write_state(
            {
                "status": "running",
                "regime": "Carga_Media",
                "regime_anterior": "Cruzeiro",
                "regime_changed_at": changed.isoformat(timespec="seconds"),
                "last_cycle_at": datetime.now().isoformat(timespec="milliseconds"),
                "interval_seconds": 5,
                "pid": 1234,
            },
            path=self.state,
        )
        online = sim.simulator_status(control_path=self.control, state_path=self.state)
        self.assertTrue(online["simulador_online"])
        self.assertEqual(online["regime_ativo"], "Carga_Media")
        self.assertEqual(online["regime_anterior"], "Cruzeiro")
        self.assertGreaterEqual(online["segundos_desde_transicao"], 29)

    def test_stop_request_preserves_selected_regime(self) -> None:
        sim.write_control("Carga_Alta", path=self.control)
        stopped = sim.request_stop(
            control_path=self.control, state_path=self.state
        )
        self.assertEqual(stopped["regime"], "Carga_Alta")
        self.assertEqual(stopped["action"], "stop")

    def test_singleton_lock_prevents_duplicate_process(self) -> None:
        lock_path = self.dir / "simulator.lock"
        first = sim.SimulatorLock(lock_path)
        second = sim.SimulatorLock(lock_path)
        try:
            self.assertTrue(first.acquire())
            self.assertFalse(second.acquire(), "Segunda instância não pode obter o lock")
        finally:
            first.release()
            second.release()
        third = sim.SimulatorLock(lock_path)
        try:
            self.assertTrue(third.acquire(), "Lock deve ser liberado ao encerrar")
        finally:
            third.release()


class HistoryMigrationTests(unittest.TestCase):
    def test_old_schema_is_migrated_without_losing_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "old.sqlite3"
            now = datetime.now().isoformat(sep=" ")
            reading = {
                "timestamp": now,
                "id_equipamento": "TURB-101",
                "modo_operacao": "Carga_Media",
                "horas_operacao_acumuladas": 4000.0,
                "temperatura_mancal_c": 62.0,
                "vibracao_rms_mms": 2.5,
                "pressao_oleo_bar": 4.2,
                "rotacao_rpm": 3000.0,
                "emissao_acustica_db": 52.0,
                "corrente_eletrica_amp": 28.0,
            }
            result = {
                "timestamp": now,
                "id_equipamento": "TURB-101",
                "modo_operacao": "Carga_Media",
                "classe_prevista": 0,
                "nome_classe_prevista": "Normal",
                "probabilidades": {"0": 0.9, "1": 0.04, "2": 0.03, "3": 0.03},
                "anomalia": False,
                "tempo_inferencia_ms": 12.0,
            }
            connection = sqlite3.connect(db_path)
            connection.execute(
                """CREATE TABLE predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    equipment_id TEXT NOT NULL,
                    reading_json TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    predicted_class INTEGER NOT NULL,
                    anomaly INTEGER,
                    inference_ms REAL NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            connection.execute(
                """INSERT INTO predictions
                (timestamp, equipment_id, reading_json, result_json,
                 predicted_class, anomaly, inference_ms)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    now,
                    "TURB-101",
                    json.dumps(reading),
                    json.dumps(result),
                    0,
                    0,
                    12.0,
                ),
            )
            connection.commit()
            connection.close()

            history = PredictionHistory(db_path)

            check = sqlite3.connect(db_path)
            try:
                columns = {row[1] for row in check.execute("PRAGMA table_info(predictions)")}
                row = check.execute(
                    "SELECT COUNT(*), regime_operacional, origem_leitura, "
                    "probabilities_json FROM predictions"
                ).fetchone()
            finally:
                check.close()
            self.assertTrue(
                {
                    "regime_operacional",
                    "origem_leitura",
                    "probabilities_json",
                    "perfil_sintetico",
                    "perfil_anomalia",
                }.issubset(columns)
            )
            self.assertEqual(row[0], 1, "A migração não pode apagar registros")
            self.assertEqual(row[1], "Carga_Media")
            self.assertEqual(row[2], "simulada")
            self.assertIn("0.9", row[3])
            self.assertEqual(len(history.list(10)), 1)

    def test_stats_separate_generated_profiles_from_predicted_classes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "stats.sqlite3"
            history = PredictionHistory(db_path)
            cases = [
                ("nominal", None, 0, "Normal", {"0": 0.8, "1": 0.1, "2": 0.05, "3": 0.05}, 10.0),
                ("anormal", "A", 3, "Cavitacao_Superaquecimento", {"0": 0.1, "1": 0.1, "2": 0.1, "3": 0.7}, 20.0),
                ("anormal", "C", 2, "Desbalanceamento_Rotor", {"0": 0.05, "1": 0.2, "2": 0.7, "3": 0.05}, 30.0),
            ]
            for profile, anomaly_profile, class_id, class_name, probabilities, inference in cases:
                timestamp = datetime.now().isoformat(sep=" ")
                reading = {
                    "timestamp": timestamp,
                    "id_equipamento": "TURB-101",
                    "modo_operacao": "Carga_Alta",
                    "regime_operacional": "Carga_Alta",
                    "origem_leitura": "simulada",
                    "perfil_sintetico": profile,
                    "perfil_anomalia": anomaly_profile,
                    "horas_operacao_acumuladas": 4000.0,
                    "temperatura_mancal_c": 80.0,
                    "vibracao_rms_mms": 6.0,
                    "pressao_oleo_bar": 4.0,
                    "rotacao_rpm": 3500.0,
                    "emissao_acustica_db": 70.0,
                    "corrente_eletrica_amp": 45.0,
                }
                result = {
                    "timestamp": timestamp,
                    "id_equipamento": "TURB-101",
                    "modo_operacao": "Carga_Alta",
                    "regime_operacional": "Carga_Alta",
                    "origem_leitura": "simulada",
                    "perfil_sintetico": profile,
                    "perfil_anomalia": anomaly_profile,
                    "classe_prevista": class_id,
                    "nome_classe_prevista": class_name,
                    "tipo_falha_predita": class_name,
                    "probabilidades": probabilities,
                    "anomalia": class_id != 0,
                    "tempo_inferencia_ms": inference,
                }
                history.add(reading, result)

            # Linha histórica anterior à migração: não tem perfil e não pode
            # contaminar a distribuição de reação do coorte com perfil.
            timestamp = datetime.now().isoformat(sep=" ")
            old_reading = {
                "timestamp": timestamp,
                "id_equipamento": "TURB-101",
                "modo_operacao": "Carga_Alta",
                "regime_operacional": "Carga_Alta",
                "origem_leitura": "simulada",
                "horas_operacao_acumuladas": 4000.0,
                "temperatura_mancal_c": 80.0,
                "vibracao_rms_mms": 6.0,
                "pressao_oleo_bar": 4.0,
                "rotacao_rpm": 3500.0,
                "emissao_acustica_db": 70.0,
                "corrente_eletrica_amp": 45.0,
            }
            old_result = {
                "timestamp": timestamp,
                "id_equipamento": "TURB-101",
                "modo_operacao": "Carga_Alta",
                "regime_operacional": "Carga_Alta",
                "origem_leitura": "simulada",
                "classe_prevista": 1,
                "nome_classe_prevista": "Desgaste_Rolamento",
                "tipo_falha_predita": "Desgaste_Rolamento",
                "probabilidades": {"0": 0.9, "1": 0.05, "2": 0.03, "3": 0.02},
                "anomalia": True,
                "tempo_inferencia_ms": 100.0,
            }
            history.add(old_reading, old_result)

            stats = history.stats()
            evaluation = stats["avaliacao_por_regime"]["Carga_Alta"]
            self.assertEqual(evaluation["leituras"], 4)
            self.assertEqual(evaluation["leituras_com_perfil"], 3)
            self.assertEqual(evaluation["leituras_sem_perfil"], 1)
            self.assertEqual(evaluation["nominais"], 1)
            self.assertEqual(evaluation["anormais"], 2)
            self.assertAlmostEqual(evaluation["proporcao_nominal_gerada"], 1 / 3, places=4)
            self.assertAlmostEqual(evaluation["proporcao_anormal_gerada"], 2 / 3, places=4)
            self.assertEqual(evaluation["classes_previstas"], {"0": 1, "2": 1, "3": 1})
            self.assertEqual(
                evaluation["classes_previstas_todas"],
                {"0": 1, "1": 1, "2": 1, "3": 1},
            )
            self.assertEqual(evaluation["perfis_anomalia"], {"A": 1, "C": 1})
            self.assertEqual(evaluation["tempo_medio_inferencia_ms"], 20.0)
            self.assertEqual(evaluation["tempo_medio_inferencia_todas_ms"], 40.0)
            self.assertAlmostEqual(
                evaluation["probabilidade_media_por_classe"]["0"],
                (0.8 + 0.1 + 0.05) / 3,
                places=4,
            )
            self.assertIn(
                "proporções nominais/anormais", stats["aviso"]
            )


class ChartTransitionTests(unittest.TestCase):
    def test_transition_lines_and_labels_are_drawn(self) -> None:
        start = datetime.now() - timedelta(minutes=5)
        rows = []
        for index in range(9):
            regime = "Cruzeiro" if index < 3 else ("Carga_Media" if index < 6 else "Carga_Alta")
            rows.append(
                {
                    "timestamp": start + timedelta(seconds=index * 30),
                    "id_equipamento": "TURB-101",
                    "regime": regime,
                    "temperatura_mancal_c": 52.0 + index * 2,
                    "vibracao_rms_mms": 1.8 + index * 0.2,
                    "anomalia": False,
                }
            )
        frame = pd.DataFrame(rows)

        figure = charts.temperature_chart(frame)
        vertical_lines = [
            shape for shape in figure.layout.shapes if shape.x0 == shape.x1
        ]
        self.assertEqual(len(vertical_lines), 2)
        labels = {annotation.text for annotation in figure.layout.annotations}
        self.assertIn("Carga Média", labels)
        self.assertIn("Carga Alta", labels)


if __name__ == "__main__":
    unittest.main()
