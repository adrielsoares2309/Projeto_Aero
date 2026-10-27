"""Testes sintéticos do segmentador de imagens térmicas coloridas."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from vision.thermal import ThermalConfig, analyze_thermal, classify_thermal_against_references


class ThermalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = np.zeros((60, 60, 3), dtype=np.uint8)
        self.image[15:35, 20:40] = (0, 0, 255)  # vermelho BGR
        self.path = self.root / "thermal.png"
        cv2.imwrite(str(self.path), self.image)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_hotspot_and_hsv_mask(self) -> None:
        result = analyze_thermal(self.path, config=ThermalConfig(morphology=False))
        self.assertEqual(result["region_count"], 1)
        self.assertEqual(result["regions"][0]["bbox"], {"x": 20, "y": 15, "width": 20, "height": 20})
        self.assertAlmostEqual(result["mask_fraction"], 400 / 3600)
        self.assertIsNone(result["temperature_measurement"])

    def test_no_hotspot_and_min_area_filter(self) -> None:
        blank = self.root / "blank.png"
        cv2.imwrite(str(blank), np.zeros((40, 40, 3), np.uint8))
        self.assertEqual(analyze_thermal(blank)["region_count"], 0)
        self.assertEqual(analyze_thermal(self.path, config=ThermalConfig(min_area=500, morphology=False))["region_count"], 0)

    def test_custom_hsv_range_and_invalid_input(self) -> None:
        # Hue 60 corresponde ao verde em OpenCV HSV.
        green_range = (((50, 200, 200), (70, 255, 255)),)
        green = np.zeros((30, 30, 3), np.uint8)
        green[5:20, 5:20] = (0, 255, 0)
        p = self.root / "green.png"
        cv2.imwrite(str(p), green)
        self.assertEqual(analyze_thermal(p, config=ThermalConfig(hsv_ranges=green_range, morphology=False))["region_count"], 1)
        with self.assertRaises(ValueError):
            ThermalConfig(hsv_ranges=(((200, 0, 0), (210, 255, 255)),))
        with self.assertRaises(ValueError):
            analyze_thermal(self.root / "missing.png")

    def test_outputs_and_original_preservation(self) -> None:
        before = self.path.read_bytes()
        result = analyze_thermal(self.path, self.root / "out", ThermalConfig(morphology=False))
        self.assertTrue(all(Path(p).exists() for p in result["outputs"].values()))
        self.assertEqual(before, self.path.read_bytes())

    def test_array_input_returns_mask_and_annotation_in_memory(self) -> None:
        result = analyze_thermal(self.image, config=ThermalConfig(morphology=False), include_artifacts=True)
        self.assertEqual(result["path"], "<imagem em memória>")
        self.assertEqual(result["region_count"], 1)
        self.assertEqual(set(result["artifacts"]), {"mask", "annotated"})
        self.assertFalse(result["outputs"])

    def test_grayscale_rejected(self) -> None:
        p = self.root / "gray.png"
        cv2.imwrite(str(p), np.zeros((20, 20), np.uint8))
        with self.assertRaises(ValueError):
            analyze_thermal(p)

    def test_real_thermal_references_are_compared_by_pixels(self) -> None:
        root = Path(__file__).resolve().parents[1] / "data/raw/imagens"
        normal = cv2.imread(str(root / "turbina_normal.png"))
        overheated = cv2.imread(str(root / "turbina_aquecimento.png"))
        self.assertIsNotNone(normal)
        self.assertIsNotNone(overheated)
        self.assertEqual(classify_thermal_against_references(normal, normal, overheated)["classification"], "TEMPERATURA NORMAL")
        self.assertEqual(classify_thermal_against_references(overheated, normal, overheated)["classification"], "SUPERAQUECIMENTO")


if __name__ == "__main__":
    unittest.main()
