import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile
import yaml
from tools.package_plugin import build_package

ORIGIN = 'https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev'


class PackageTests(unittest.TestCase):
    def test_shared_service_export_has_no_origin_field(self):
        with tempfile.TemporaryDirectory() as directory:
            path = build_package(Path(directory) / 'recipe.zip')
            with ZipFile(path) as archive:
                self.assertIsNone(archive.testzip())
                settings = yaml.safe_load(archive.read('settings.yml'))
                self.assertTrue(settings['polling_url'].startswith(ORIGIN + '/api/visibility?'))
                fields = {f['keyname']: f for f in settings['custom_fields']}
                self.assertNotIn('service_url', fields)
                self.assertIs(fields['show_feedback_qr']['default'], False)
                self.assertIn("assign image_origin = '" + ORIGIN + "'", archive.read('shared.liquid').decode())

    def test_maintainer_override_updates_polling_and_artwork_without_source_edits(self):
        root = Path(__file__).resolve().parents[1] / 'plugin/src'
        before = {p: p.read_bytes() for p in root.iterdir() if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            path = build_package(Path(directory) / 'recipe.zip', 'http://127.0.0.1:8787/', True)
            with ZipFile(path) as archive:
                settings = yaml.safe_load(archive.read('settings.yml'))
                self.assertTrue(settings['polling_url'].startswith('http://127.0.0.1:8787/api/visibility?'))
                shared = archive.read('shared.liquid').decode()
                self.assertIn("assign image_origin = 'http://127.0.0.1:8787'", shared)
                self.assertNotIn(ORIGIN, shared)
                fields = {f['keyname']: f for f in settings['custom_fields']}
                self.assertNotIn('service_url', fields)
                self.assertIs(fields['show_feedback_qr']['default'], True)
        self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_invalid_origin_cannot_create_an_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'recipe.zip'
            for value in ('http://public.example.com', 'https://user:password@example.com',
                          'https://example.com/path', "https://bad'host.example.com"):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    build_package(path, value)
                self.assertFalse(path.exists())
