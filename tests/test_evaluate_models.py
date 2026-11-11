import json
import unittest
from tools.evaluate_models import evaluate_reports, read_reports, utc_timestamp


def report(v1='not_out', v2='mountain_out', answer='out', received=1000, version='seattle-corridor-v2-candidate'):
    return dict(received=received, mountain='rainier', viewpoint='seattle', answer=answer,
                snapshot=dict(status='not_out', submission_weather_estimate=dict(model_comparison=dict(
                    v1=dict(model='seattle-corridor-v1-uncalibrated', status=v1),
                    v2=dict(model=version, status=v2)))))


class EvaluationTests(unittest.TestCase):
    def test_uses_submission_models_and_reports_abstention_and_paired_counts(self):
        legacy = report()
        legacy['snapshot'] = {'status': 'mountain_out'}
        data = [report(), report(v1='unknown'), report(v2='unknown'), report(answer='unsure'), legacy]
        result = evaluate_reports(data)
        self.assertEqual(result['reports_used'], 3)
        self.assertEqual(result['skipped'], {'uncertain_observation': 1, 'legacy_display_only': 1})
        cohort = result['cohorts'][0]
        self.assertEqual(cohort['v1'], dict(same=0, different=2, uncompared=1))
        self.assertEqual(cohort['v2'], dict(same=2, different=0, uncompared=1))
        self.assertEqual(cohort['paired_comparable'], 1)
        self.assertEqual(cohort['paired']['only_v2_same'], 1)

    def test_dates_viewpoints_and_versions_are_not_silently_pooled(self):
        data = [report(received=9), report(received=10), report(received=11, version='future-v3'), report(received=20)]
        result = evaluate_reports(data, since=10, until=20)
        self.assertEqual(result['skipped']['outside_period'], 2)
        self.assertEqual(len(result['cohorts']), 2)
        self.assertEqual(utc_timestamp('2026-11-11'), utc_timestamp('2026-11-11T00:00:00Z'))

    def test_wrangler_json_and_json_lines_support_string_snapshots_and_reject_bad_rows(self):
        row = report()
        row['snapshot'] = json.dumps(row['snapshot'])
        wrapped = json.dumps([{'results': [row], 'success': True}])
        self.assertEqual(evaluate_reports(read_reports(wrapped))['reports_used'], 1)
        lines = json.dumps(row) + '\n' + json.dumps({'answer': 'made_up'}) + '\n'
        result = evaluate_reports(read_reports(lines))
        self.assertEqual(result['reports_used'], 1)
        self.assertEqual(result['skipped']['malformed'], 1)
