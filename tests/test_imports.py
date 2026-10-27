"""Verifica imports centrais sem iniciar processos de serviço."""
from __future__ import annotations

import importlib
import unittest


class ModuleImportTests(unittest.TestCase):
    def test_application_modules_import_without_starting_services(self) -> None:
        modules = (
            "api.main",
            "api.history",
            "api.predictor",
            "api.schemas",
            "frontend.api_client",
            "frontend.charts",
            "frontend.components",
            "frontend.icons",
            "frontend.styles",
            "frontend.app",
            "vision.geometry",
            "vision.thermal",
            "vision.pipeline",
            "simulator",
        )
        for module_name in modules:
            with self.subTest(module=module_name):
                importlib.import_module(module_name)

    def test_frontend_vision_symbols_exist_at_expected_paths(self) -> None:
        geometry = importlib.import_module("vision.geometry")
        thermal = importlib.import_module("vision.thermal")
        for symbol in (
            "GeometryConfig",
            "load_image",
            "analyze_geometry",
            "classify_geometry_against_references",
        ):
            with self.subTest(module="vision.geometry", symbol=symbol):
                self.assertTrue(callable(getattr(geometry, symbol)))
        for symbol in (
            "ThermalConfig",
            "analyze_thermal",
            "classify_thermal_against_references",
        ):
            with self.subTest(module="vision.thermal", symbol=symbol):
                self.assertTrue(callable(getattr(thermal, symbol)))


if __name__ == "__main__":
    unittest.main()
