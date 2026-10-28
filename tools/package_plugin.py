"""Build the native TRMNL import archive; optional defaults for a specific host."""
import argparse
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service-url')
    parser.add_argument('--enable-feedback', action='store_true')
    parser.add_argument('--output', default='.local/exports/is-the-mountain-out-responsive.zip')
    args = parser.parse_args()
    settings = yaml.safe_load((ROOT / 'plugin/src/settings.yml').read_text())
    for field in settings['custom_fields']:
        if field['keyname'] == 'service_url' and args.service_url:
            field['default'] = args.service_url.rstrip('/')
        if field['keyname'] == 'show_feedback_qr' and args.enable_feedback:
            field['default'] = True
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for file in sorted((ROOT / 'plugin/src').glob('*.liquid')):
            archive.write(file, file.name)
        archive.writestr('settings.yml', yaml.safe_dump(settings, sort_keys=False, allow_unicode=True))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {'settings.yml', 'shared.liquid', 'full.liquid', 'half_horizontal.liquid', 'half_vertical.liquid', 'quadrant.liquid'}
    print(output.resolve())


if __name__ == '__main__':
    main()
