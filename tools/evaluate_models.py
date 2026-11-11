"""Compare model agreement with private, unverified reports at submission time."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from math import isfinite
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mountain.feedback import CHOICES, comparison

STATUSES = {'not_out', 'kinda_out', 'halfway_out', 'mostly_out', 'mountain_out', 'unknown'}


def read_reports(text):
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = [json.loads(line) for line in text.splitlines() if line.strip()]
    entries = data if isinstance(data, list) else [data]
    for entry in entries:
        if isinstance(entry, dict) and isinstance(entry.get('results'), list):
            yield from entry['results']  # Wrangler D1 --json output.
        else:
            yield entry


def evaluate_reports(reports, since=None, until=None):
    skipped, cohorts = Counter(), {}
    seen = 0
    for report in reports:
        seen += 1
        try:
            if not isinstance(report, dict) or report.get('answer') not in CHOICES:
                raise ValueError('Malformed report')
            received = report.get('received')
            if isinstance(received, bool) or not isinstance(received, (int, float)) or not isfinite(received):
                raise ValueError('Missing report timestamp')
            if (since is not None and received < since) or (until is not None and received >= until):
                skipped['outside_period'] += 1
                continue
            if report['answer'] == 'unsure':
                skipped['uncertain_observation'] += 1
                continue
            snapshot = report.get('snapshot', {})
            if isinstance(snapshot, str):
                snapshot = json.loads(snapshot)
            if not isinstance(snapshot, dict):
                raise ValueError('Malformed snapshot')
            fresh = snapshot.get('submission_weather_estimate')
            if fresh is None:
                skipped['legacy_display_only'] += 1
                continue
            models = fresh.get('model_comparison', {})
            v1, v2 = models.get('v1'), models.get('v2')
            if not isinstance(v1, dict) or not isinstance(v2, dict):
                skipped['missing_model_comparison'] += 1
                continue
            if any(m.get('status') not in STATUSES or not isinstance(m.get('model'), str) for m in (v1, v2)):
                raise ValueError('Malformed model result')
            mountain = report.get('mountain') or fresh.get('mountain') or snapshot.get('mountain')
            viewpoint = report.get('viewpoint') or fresh.get('viewpoint') or snapshot.get('viewpoint')
            if not isinstance(mountain, str) or not isinstance(viewpoint, str):
                raise ValueError('Missing viewpoint')
            key = (mountain, viewpoint, v1['model'], v2['model'])
            if key not in cohorts:
                cohorts[key] = dict(mountain=mountain, viewpoint=viewpoint, v1_model=v1['model'], v2_model=v2['model'],
                                    reports=0, v1=dict(same=0, different=0, uncompared=0),
                                    v2=dict(same=0, different=0, uncompared=0), paired_comparable=0,
                                    paired=dict(both_same=0, only_v1_same=0, only_v2_same=0, both_different=0))
            cohort = cohorts[key]
            one, two = comparison(v1['status'], report['answer']), comparison(v2['status'], report['answer'])
            cohort['reports'] += 1
            cohort['v1'][one] += 1
            cohort['v2'][two] += 1
            if one != 'uncompared' and two != 'uncompared':
                cohort['paired_comparable'] += 1
                outcome = 'both_same' if one == two == 'same' else 'only_v1_same' if one == 'same' else 'only_v2_same' if two == 'same' else 'both_different'
                cohort['paired'][outcome] += 1
        except (ValueError, TypeError, AttributeError):
            skipped['malformed'] += 1
    return dict(basis='Agreement with unverified, self-reported observations; not measured accuracy.',
                reports_seen=seen, reports_used=sum(c['reports'] for c in cohorts.values()), skipped=dict(skipped),
                cohorts=[cohorts[key] for key in sorted(cohorts)])


def utc_timestamp(value):
    parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)).timestamp()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', nargs='?', default='-', help='Private JSONL/JSON/D1 export; - reads stdin.')
    parser.add_argument('--since', type=utc_timestamp, help='Inclusive ISO time/date; dates without offsets use UTC.')
    parser.add_argument('--until', type=utc_timestamp, help='Exclusive ISO time/date; dates without offsets use UTC.')
    args = parser.parse_args()
    if args.since is not None and args.until is not None and args.since >= args.until:
        parser.error('--since must be before --until')
    text = sys.stdin.read() if args.input == '-' else Path(args.input).read_text()
    print(json.dumps(evaluate_reports(read_reports(text), args.since, args.until), indent=2))


if __name__ == '__main__':
    main()
