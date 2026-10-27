import unittest
from pathlib import Path
from tools.preview import render, STATES, SIZES
import yaml


class TemplateTests(unittest.TestCase):
    def test_every_layout_and_state(self):
        for layout in SIZES:
            scenes = []
            for state in STATES:
                with self.subTest(layout=layout, state=state):
                    html = render(state, layout)
                    self.assertNotIn('Estimate for', html)
                    self.assertNotIn('Oct 27', html)
                    self.assertNotIn('<style>', html)
                    self.assertIn('layout layout--col', html)
                    self.assertIn('value ', html)
                    if state != 'unknown':
                        self.assertIn('/assets/rainier-seattle.png', html)
                    else:
                        self.assertIn('stroke-dasharray', html)
                    self.assertNotIn('{%', html)

    def test_state_artwork_changes(self):
        scenes = [render(state).split('<svg', 1)[1].split('</svg>', 1)[0] for state in STATES]
        self.assertEqual(len(set(scenes)), 6)
        self.assertNotIn('<image', scenes[-1])
        self.assertIn('translate(0 -60)', scenes[0])
        self.assertIn('translate(0 175)', scenes[3])
        self.assertNotIn('<g transform', scenes[4])
        for scene in scenes[:4]:
            self.assertIn('/assets/cloud-bank.png', scene)
        self.assertNotIn('/assets/cloud-bank.png', scenes[4])

    def test_user_text_is_escaped(self):
        html = render(verdict='<script>alert(1)</script>')
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)

    def test_missing_data_neutral(self):
        html = render('unknown', verdict=None)
        self.assertIn('UNKNOWN', html)
        self.assertNotIn('MOUNTAIN OUT', html)

    def test_settings(self):
        settings = yaml.safe_load(Path('plugin/src/settings.yml').read_text())
        fields = {f['keyname'] for f in settings['custom_fields']}
        self.assertTrue({'mountain', 'rainier_viewpoint', 'hood_viewpoint', 'service_url'} <= fields)
        self.assertEqual(settings['strategy'], 'polling')
        self.assertEqual(settings['framework_version'], '3.4.0')
