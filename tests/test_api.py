"""Testes da API usando os artefatos reais do projeto.

O banco é redirecionado para um diretório temporário para não poluir o
histórico real do dashboard.
"""
from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

_TEMP_DIR = tempfile.TemporaryDirectory()
os.environ["AEROMOTION_DB_PATH"] = str(Path(_TEMP_DIR.name) / "predictions.sqlite3")

from fastapi.testclient import TestClient  # noqa: E402

import simulator  # noqa: E402
from api.main import app  # noqa: E402


def reading(equipment: str = "TURB-102", **overrides) -> dict:
    payload = {
        "timestamp": datetime.now().isoformat(),
        "id_equipamento": equipment,
        "modo_operacao": "Carga_Media",
        "origem_leitura": "simulada",
        "horas_operacao_acumuladas": 4000.0,
        "temperatura_mancal_c": 64.0,
        "vibracao_rms_mms": 3.1,
        "pressao_oleo_bar": 4.2,
        "rotacao_rpm": 3000.0,
        "emissao_acustica_db": 52.0,
        "corrente_eletrica_amp": 30.0,
    }
    payload.update(overrides)
    return payload


def tearDownModule() -> None:
    _TEMP_DIR.cleanup()


class ApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        runtime = Path(self.tmp.name)
        self.control_patch = patch.object(
            simulator, "CONTROL_FILE", runtime / "simulator_control.json"
        )
        self.state_patch = patch.object(
            simulator, "STATE_FILE", runtime / "simulator_state.json"
        )
        self.control_patch.start()
        self.state_patch.start()

    def tearDown(self) -> None:
        self.control_patch.stop()
        self.state_patch.stop()
        self.tmp.cleanup()

    def test_health_prediction_history_and_stats(self) -> None:
        with TestClient(app) as client:
            self.assertEqual(client.get("/health").status_code, 200)
            response = client.post(
                "/predict",
                json=reading(
                    perfil_sintetico="anormal",
                    perfil_anomalia="A",
                ),
            )
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertIn("probabilidades", body)
            self.assertIn("regime_operacional", body)
            self.assertEqual(body["origem_leitura"], "simulada")
            self.assertEqual(body["perfil_sintetico"], "anormal")
            self.assertEqual(body["perfil_anomalia"], "A")
            self.assertEqual(body["tipo_falha_predita"], body["nome_classe_prevista"])
            self.assertEqual(client.get("/predictions?limit=5").status_code, 200)
            stats = client.get("/stats")
            self.assertEqual(stats.status_code, 200)
            payload = stats.json()
            self.assertIn("predicoes_por_regime", payload)
            self.assertIn("predicoes_por_origem", payload)
            self.assertIn("avaliacao_por_regime", payload)
            self.assertIn("Carga_Alta", payload["avaliacao_por_regime"])

    def test_invalid_reading_is_rejected(self) -> None:
        payload = reading()
        payload["vibracao_rms_mms"] = -1
        with TestClient(app) as client:
            self.assertEqual(client.post("/predict", json=payload).status_code, 422)

    def test_regime_endpoints(self) -> None:
        with TestClient(app) as client:
            listed = client.get("/regimes")
            self.assertEqual(listed.status_code, 200)
            self.assertEqual(
                set(listed.json()["regimes"]),
                {"Cruzeiro", "Carga_Media", "Carga_Alta"},
            )

            response = client.post("/regime", json={"regime": "Carga_Alta"})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["regime_selecionado"], "Carga_Alta")

            status = client.get("/regime").json()
            self.assertEqual(status["regime_selecionado"], "Carga_Alta")
            self.assertFalse(status["simulador_online"])
            self.assertEqual(simulator.read_control()["regime"], "Carga_Alta")

            invalid = client.post("/regime", json={"regime": "Turbo_Maximo"})
            self.assertEqual(invalid.status_code, 422)

    def test_predicted_class_is_model_output_not_forced_by_regime(self) -> None:
        base = reading(
            equipment="TURB-103",
            modo_operacao="Carga_Alta",
            temperatura_mancal_c=72.0,
            vibracao_rms_mms=3.8,
            pressao_oleo_bar=4.8,
            rotacao_rpm=3500.0,
            emissao_acustica_db=62.0,
            corrente_eletrica_amp=38.0,
        )
        first = dict(base)
        first["regime_operacional"] = "Carga_Alta"
        first["origem_leitura"] = "simulada"
        first["perfil_sintetico"] = "nominal"

        second = dict(base)
        second["id_equipamento"] = "TURB-104"
        second["regime_operacional"] = "Cruzeiro"
        second["origem_leitura"] = "real"
        second["perfil_sintetico"] = "anormal"
        second["perfil_anomalia"] = "A"

        with TestClient(app) as client:
            response_a = client.post("/predict", json=first)
            response_b = client.post("/predict", json=second)
            self.assertEqual(response_a.status_code, 200)
            self.assertEqual(response_b.status_code, 200)
            body_a, body_b = response_a.json(), response_b.json()

        # O regime é metadado operacional: não é feature e não altera a classe.
        self.assertEqual(body_a["classe_prevista"], body_b["classe_prevista"])
        self.assertEqual(body_a["probabilidades"], body_b["probabilidades"])
        self.assertEqual(body_a["regime_operacional"], "Carga_Alta")
        self.assertEqual(body_b["regime_operacional"], "Cruzeiro")
        self.assertEqual(body_a["origem_leitura"], "simulada")
        self.assertEqual(body_b["origem_leitura"], "real")
        self.assertEqual(body_a["perfil_sintetico"], "nominal")
        self.assertEqual(body_b["perfil_sintetico"], "anormal")
        self.assertEqual(body_b["perfil_anomalia"], "A")
        self.assertIn(body_a["classe_prevista"], (0, 1, 2, 3))
        # O perfil é metadado do gerador; não entra nas features nem na saída.
        self.assertNotIn("perfil_sintetico", body_a["sensores"])
        self.assertNotIn("perfil_anomalia", body_a["sensores"])

    def test_profile_metadata_is_persisted_without_becoming_a_feature(self) -> None:
        payload = reading(
            equipment="TURB-104",
            modo_operacao="Carga_Alta",
            perfil_sintetico="anormal",
            perfil_anomalia="B",
            temperatura_mancal_c=78.0,
            vibracao_rms_mms=9.0,
            pressao_oleo_bar=4.7,
            rotacao_rpm=3500.0,
            emissao_acustica_db=82.0,
            corrente_eletrica_amp=40.0,
        )
        with TestClient(app) as client:
            response = client.post("/predict", json=payload)
            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["perfil_sintetico"], "anormal")
            self.assertEqual(body["perfil_anomalia"], "B")
            self.assertEqual(body["tipo_falha_predita"], body["nome_classe_prevista"])
            self.assertNotIn("perfil_sintetico", body["sensores"])
            self.assertNotIn("perfil_anomalia", body["sensores"])

            history = client.get("/predictions?limit=100").json()["items"]
            persisted = [
                item
                for item in history
                if item.get("id_equipamento") == "TURB-104"
                and item.get("perfil_anomalia") == "B"
            ]
            self.assertTrue(persisted)
            self.assertEqual(persisted[0]["perfil_sintetico"], "anormal")

    def test_stats_report_generated_proportions_and_predicted_classes(self) -> None:
        nominal_payload = reading(
            equipment="TURB-101",
            modo_operacao="Carga_Alta",
            perfil_sintetico="nominal",
            temperatura_mancal_c=72.0,
            vibracao_rms_mms=3.8,
            pressao_oleo_bar=4.8,
            rotacao_rpm=3500.0,
            emissao_acustica_db=62.0,
            corrente_eletrica_amp=38.0,
        )
        anomaly_payload = reading(
            equipment="TURB-102",
            modo_operacao="Carga_Alta",
            perfil_sintetico="anormal",
            perfil_anomalia="C",
            temperatura_mancal_c=84.0,
            vibracao_rms_mms=10.5,
            pressao_oleo_bar=4.6,
            rotacao_rpm=3500.0,
            emissao_acustica_db=64.0,
            corrente_eletrica_amp=52.0,
        )
        with TestClient(app) as client:
            self.assertEqual(client.post("/predict", json=nominal_payload).status_code, 200)
            self.assertEqual(client.post("/predict", json=anomaly_payload).status_code, 200)
            stats = client.get("/stats").json()
        evaluation = stats["avaliacao_por_regime"]["Carga_Alta"]
        self.assertGreaterEqual(evaluation["nominais"], 1)
        self.assertGreaterEqual(evaluation["anormais"], 1)
        self.assertIsNotNone(evaluation["proporcao_nominal_gerada"])
        self.assertIsNotNone(evaluation["proporcao_anormal_gerada"])
        self.assertIn("C", evaluation["perfis_anomalia"])
        self.assertTrue(evaluation["classes_previstas"])
        self.assertIsNotNone(evaluation["tempo_medio_inferencia_ms"])
        self.assertTrue(evaluation["probabilidade_media_por_classe"])
        self.assertIn("proporções nominais/anormais", stats["aviso"])

    def test_regime_switch_does_not_create_new_simulator_process(self) -> None:
        with TestClient(app) as client:
            client.post("/regime", json={"regime": "Carga_Media"})
            client.post("/regime", json={"regime": "Carga_Alta"})
            client.post("/regime", json={"regime": "Cruzeiro"})
        # Todo comando é persistido no mesmo arquivo de controle; nenhum
        # processo é iniciado pela API.
        control = simulator.read_control()
        self.assertEqual(control["regime"], "Cruzeiro")
        self.assertEqual(control["action"], "run")


if __name__ == "__main__":
    unittest.main()
