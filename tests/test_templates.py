import unittest
from pathlib import Path
from tools.preview import render, STATES, SIZES
import yaml

ORIGIN = 'https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev'

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
            # The scene and verdict remain separate responsive regions; actual
            # bounds and QR placement are exercised by tools/check_layouts.py.
            self.assertEqual(html.count('data-mountain-region'), 1)
            self.assertEqual(html.count('data-verdict-region'), 1)
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
        self.assertEqual(fields, {'author_bio', 'mountain', 'rainier_viewpoint', 'hood_viewpoint', 'show_feedback_qr'})
        self.assertEqual(settings['strategy'], 'polling')
        self.assertEqual(settings['framework_version'], '3.4.0')

    def test_polling_uses_active_mountain_fields_and_feedback_encodings(self):
        from liquid import Environment
        from urllib.parse import urlsplit, parse_qs
        settings = yaml.safe_load(Path('plugin/src/settings.yml').read_text())
        polling = Environment().from_string(settings['polling_url'])
        # Saved fields from the hidden dropdown must not select the other mountain.
        for mountain, viewpoint in [('rainier', 'tacoma'), ('hood', 'portland')]:
            for feedback in [True, False, 'true', 'false', 'yes', 'no', 'on', 'off', 1, 0]:
                with self.subTest(mountain=mountain, feedback=feedback):
                    url = polling.render(mountain=mountain, rainier_viewpoint='tacoma',
                                         hood_viewpoint='portland', show_feedback_qr=feedback)
                    self.assertEqual(urlsplit(url).scheme + '://' + urlsplit(url).netloc, ORIGIN)
                    query = parse_qs(urlsplit(url).query)
                    self.assertEqual(query['mountain'], [mountain])
                    self.assertEqual(query['viewpoint'], [viewpoint])
                    enabled = query['feedback'][0].lower() in ('true', 'yes', 'on', '1')
                    self.assertEqual(enabled, feedback in (True, 'true', 'yes', 'on', 1))
        defaults = parse_qs(urlsplit(polling.render()).query)
        self.assertEqual(defaults, {'mountain': ['rainier'], 'viewpoint': ['seattle'], 'feedback': ['false']})

    def test_shared_service_needs_no_settings_and_ignores_legacy_origin(self):
        from tools.preview import qr_code
        legacy = {'plugin_settings': {'custom_fields_values': {'service_url': 'https://old.example.com'}}}
        for layout in SIZES:
            for fields in ({}, {'trmnl': legacy}):
                with self.subTest(layout=layout, legacy=bool(fields)):
                    html = render('halfway_out', layout, feedback_qr_path='/q/example', **fields)
                    self.assertIn(f'href="{ORIGIN}/assets/rainier-seattle.png"', html)
                    self.assertIn(f'href="{ORIGIN}/assets/cloud-bank.png"', html)
                    self.assertNotIn('old.example.com', html)
                    if layout == 'full':
                        svg = qr_code(ORIGIN + '/f/example').replace('class="qr-code"', 'class="qr-code w--full h--auto block"')
                        self.assertIn(svg, html)
