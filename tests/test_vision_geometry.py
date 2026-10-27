"""Testes sintéticos e determinísticos do processamento geométrico."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import cv2
import numpy as np

from vision.geometry import GeometryConfig, analyze_geometry, contour_features, load_image, classify_geometry_against_references
from vision.pipeline import diagnose_image_dataset, inspect_training_data, predict_image, train_classifier


class GeometryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.image = np.zeros((100, 100, 3), dtype=np.uint8)
        cv2.circle(self.image, (50, 50), 20, (255, 255, 255), -1)
        self.path = self.root / "circle.png"
        cv2.imwrite(str(self.path), self.image)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_load_valid_and_missing_image(self) -> None:
        self.assertEqual(load_image(self.path).shape, self.image.shape)
        with self.assertRaises(ValueError):
            load_image(self.root / "missing.png")

    def test_gray_edges_contours_and_features(self) -> None:
        result = analyze_geometry(self.path)
        self.assertEqual((result["width"], result["height"], result["channels"]), (100, 100, 3))
        self.assertGreater(result["contour_count"], 0)
        feature = result["contours"][0]
        self.assertGreater(feature["area"], 0)
        self.assertGreater(feature["perimeter"], 0)
        self.assertIsNotNone(feature["circularity"])
        self.assertIsNotNone(feature["centroid"])
        self.assertGreaterEqual(feature["aspect_ratio"], 0)

    def test_perimeter_zero_and_blank_input(self) -> None:
        line = np.array([[[1, 1]], [[1, 1]]], dtype=np.int32)
        self.assertIsNone(contour_features(line)["circularity"])
        blank = self.root / "blank.png"
        cv2.imwrite(str(blank), np.zeros((40, 40, 3), np.uint8))
        self.assertEqual(analyze_geometry(blank)["contour_count"], 0)

    def test_array_input_returns_visual_artifacts_without_persisting_upload(self) -> None:
        result = analyze_geometry(self.image, include_artifacts=True)
        self.assertEqual(result["path"], "<imagem em memória>")
        self.assertTrue({"gray", "edges", "contours", "annotated"}.issubset(result["artifacts"]))
        self.assertFalse(result["outputs"])

    def test_missing_vision_model_is_indeterminate(self) -> None:
        prediction = predict_image(self.image, "geometrica", model_dir=self.root / "no-model")
        self.assertFalse(prediction["available"])
        self.assertEqual(prediction["class"], "indeterminada")

    def test_dataset_diagnostic_counts_classes_and_duplicate_hashes(self) -> None:
        root = self.root / "dataset"
        for class_name in ("normal", "deformada"):
            folder = root / "geometricas" / class_name
            folder.mkdir(parents=True)
            image = np.full((12, 16, 3), 20 if class_name == "normal" else 220, np.uint8)
            cv2.imwrite(str(folder / f"{class_name}.png"), image)
        report = diagnose_image_dataset(root)
        self.assertEqual(report["modality_counts"]["geometrica"], 2)
        self.assertEqual(report["class_counts"]["geometrica"], {"defeituosa": 1, "normal": 1})
        self.assertFalse(report["invalid_files"])

    def test_output_creation_and_original_preservation(self) -> None:
        before = self.path.read_bytes()
        result = analyze_geometry(self.path, self.root / "out")
        self.assertTrue(all(Path(p).exists() for p in result["outputs"].values()))
        self.assertEqual(before, self.path.read_bytes())

    def test_config_validation(self) -> None:
        with self.assertRaises(ValueError):
            GeometryConfig(gaussian_kernel=4)

    def test_real_references_are_compared_by_pixels(self) -> None:
        root = Path(__file__).resolve().parents[1] / "data/raw/imagens"
        normal = load_image(root / "geo_001_pa_normal.png")
        defective = load_image(root / "geo_001_pa_deformada.png")
        self.assertEqual(classify_geometry_against_references(normal, normal, defective)["classification"], "DENTRO DOS CONFORMES")
        self.assertEqual(classify_geometry_against_references(defective, normal, defective)["classification"], "REPROVADA")
        unrelated = np.zeros_like(normal)
        self.assertEqual(classify_geometry_against_references(unrelated, normal, defective)["classification"], "INCONCLUSIVA")

    def test_training_validation_and_small_labeled_fit(self) -> None:
        self.assertFalse(inspect_training_data(self.root)["ready_for_supervised_training"])
        self.assertFalse(train_classifier(self.root)["trained"])
        labeled = self.root / "geometricas"
        for label, radius in (("normal", 12), ("defeituosa", 24)):
            folder = labeled / label
            folder.mkdir(parents=True)
            for index in range(4):
                sample = np.zeros((64, 64, 3), np.uint8)
                cv2.circle(sample, (32, 32), radius - index % 2, (255, 255, 255), -1)
                cv2.imwrite(str(folder / f"sample_{index}.png"), sample)
        result = train_classifier(labeled.parent, model_dir=self.root / "models")
        self.assertTrue(result["trained"])
        self.assertTrue(Path(result["metadata"]["model_path"]).exists())
        self.assertTrue(Path(result["metadata_path"]).exists())


if __name__ == "__main__":
    unittest.main()
