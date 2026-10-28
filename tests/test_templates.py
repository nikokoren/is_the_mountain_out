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

    def test_native_qr_and_responsive_contract(self):
        from tools.preview import render
        for layout in SIZES:
            html = render(layout=layout, feedback_url='https://mountain.test/f/example')
            if layout == 'full':
                self.assertIn('qr-code w--full h--auto', html)
                self.assertIn('Submit report', html)
                self.assertIn('absolute bottom--0 right--0', html)
            else:
                self.assertNotIn('qr-code', html)
                self.assertNotIn('Submit report', html)
            self.assertIn('data-fit-value="true"', html)
            self.assertIn('grow w--full h--min-0', html)
            self.assertNotIn('width="112"', html)
            self.assertNotIn('height="300" viewBox', html)
        self.assertNotIn('qr-code', render())
        self.assertIn('qr-code', render(feedback_qr_path='/q/example'))

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
