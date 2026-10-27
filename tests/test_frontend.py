"""Testes de interface do controle de regime no Streamlit."""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

import frontend.api_client as client
import simulator as sim

APP_PATH = Path(__file__).resolve().parents[1] / "frontend" / "app.py"


def regime_status(active: str = "Cruzeiro") -> dict:
    return {
        "regimes_disponiveis": list(sim.REGIMES),
        "rotulos": dict(sim.REGIME_LABELS),
        "regime_selecionado": active,
        "regime_ativo": active,
        "regime_anterior": None,
        "ultima_mudanca": "2026-10-22T10:00:00",
        "segundos_desde_transicao": 12.0,
        "simulador_online": True,
        "status_simulador": "running",
        "intervalo_segundos": 5,
        "mensagem": "Simulador online.",
    }


class RegimeSidebarTests(unittest.TestCase):
    def _run_app(self, setter, getter=None):
        if getter is None:
            getter = lambda: (regime_status(), None)  # noqa: E731

        patches = [
            patch.object(client, "get_regime_status", side_effect=getter),
            patch.object(client, "set_operating_regime", new=setter),
            patch.object(client, "get_health", return_value=(None, "offline")),
            patch.object(client, "get_stats", return_value=(None, "offline")),
            patch.object(client, "is_api_online", return_value=False),
            patch.object(client, "get_predictions", return_value=({"items": []}, None)),
            patch.object(
                sim,
                "simulator_status",
                side_effect=lambda: getter()[0],
            ),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)
        app = AppTest.from_file(str(APP_PATH), default_timeout=60)
        app.run()
        return app

    def test_sidebar_exposes_exactly_three_mutually_exclusive_regime_buttons(self) -> None:
        def setter(regime: str):
            return regime_status(regime), None

        app = self._run_app(setter)
        self.assertEqual(list(app.exception), [])
        labels = [button.label for button in app.sidebar.button]
        self.assertEqual(
            [label for label in labels if label in ("Cruzeiro", "Carga Média", "Carga Alta")],
            ["Cruzeiro", "Carga Média", "Carga Alta"],
        )
        self.assertEqual(len(labels), 5, "Três regimes + Iniciar + Parar")
        markdown = " ".join(item.value for item in app.sidebar.markdown)
        self.assertIn("Regime de Operação", markdown)
        self.assertIn("Regime ativo: Cruzeiro", markdown)

        active_regimes = [
            button.label
            for button in app.sidebar.button
            if button.proto.type == "primary"
            and button.label in ("Cruzeiro", "Carga Média", "Carga Alta")
        ]
        self.assertEqual(active_regimes, ["Cruzeiro"])

    def test_clicking_regime_button_sends_one_command_and_updates_state(self) -> None:
        state = {"active": "Cruzeiro"}
        calls: list[str] = []

        def setter(regime: str):
            calls.append(regime)
            state["active"] = regime
            return regime_status(regime), None

        def getter():
            return regime_status(state["active"]), None

        app = self._run_app(setter, getter)
        app.sidebar.button(key="regime_carga_alta").click().run()

        self.assertEqual(list(app.exception), [])
        self.assertEqual(calls, ["Carga_Alta"])
        self.assertTrue(
            any("Regime ativo: Carga Alta" in item.value for item in app.sidebar.markdown)
        )

    def test_api_failure_is_reported_without_breaking_sidebar(self) -> None:
        def setter(regime: str):
            return None, "Conexão recusada — a API não está acessível."

        app = self._run_app(setter)
        app.sidebar.button(key="regime_carga_media").click().run()

        self.assertEqual(list(app.exception), [])
        errors = " ".join(item.value for item in app.sidebar.error)
        self.assertIn("Falha ao comunicar", errors)

    def test_vision_computer_page_opens_without_errors(self) -> None:
        app = self._run_app(lambda regime: (regime_status(regime), None))
        app.sidebar.radio[0].set_value("Visão Computacional").run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Visão Computacional" in item.value for item in app.markdown))

    def test_evaluation_page_renders_real_correlation_section(self) -> None:
        app = self._run_app(lambda regime: (regime_status(regime), None))
        app.sidebar.radio[0].set_value("Avaliação do Modelo").run()
        self.assertEqual(list(app.exception), [])
        self.assertTrue(any("Matriz de Correlação das Variáveis" in item.value for item in app.markdown))

if __name__ == "__main__":
    unittest.main()
