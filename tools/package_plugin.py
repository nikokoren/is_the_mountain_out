"""Build the shared-service recipe; maintainers can export a separate backend."""
import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit
from zipfile import ZipFile, ZIP_DEFLATED
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from mountain.feedback import public_origin


class PollingURL(str):
    """Keep Liquid's quotes literal and the URL on one line in the export."""


class RecipeDumper(yaml.SafeDumper):
    pass


RecipeDumper.add_representer(PollingURL, lambda dumper, value: dumper.represent_scalar(
    'tag:yaml.org,2002:str', str(value), style='"'))


def build_package(output, service_url=None, enable_feedback=False):
    settings = yaml.safe_load((ROOT / 'plugin/src/settings.yml').read_text())
    templates = {file.name: file.read_text() for file in sorted((ROOT / 'plugin/src').glob('*.liquid'))}
    polling = urlsplit(settings['polling_url'])
    source_origin = public_origin(f'{polling.scheme}://{polling.netloc}')
    origin_assignment = "{% assign image_origin = '" + source_origin + "' %}"
    if origin_assignment not in templates['shared.liquid']:
        raise ValueError('Polling and shared artwork must use the same service origin.')
    if service_url is not None:
        # This changes the exported files only, never adds an installation field.
        service_url = public_origin(service_url)
        if any(c in service_url for c in "'\"\\\n\r"):
            raise ValueError('Service origin contains invalid characters.')
        settings['polling_url'] = service_url + settings['polling_url'][len(source_origin):]
        templates['shared.liquid'] = templates['shared.liquid'].replace(
            origin_assignment, "{% assign image_origin = '" + service_url + "' %}", 1)
    for field in settings['custom_fields']:
        if field['keyname'] == 'show_feedback_qr' and enable_feedback:
            field['default'] = True
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name, markup in templates.items():
            archive.writestr(name, markup)
        export_settings = {**settings, 'polling_url': PollingURL(settings['polling_url'])}
        archive.writestr('settings.yml', yaml.dump(export_settings, Dumper=RecipeDumper,
                                               sort_keys=False, allow_unicode=True, width=4096))
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {'settings.yml', 'shared.liquid', 'full.liquid', 'half_horizontal.liquid', 'half_vertical.liquid', 'quadrant.liquid'}
    return output.resolve()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--service-url', help='Maintainer-only export override for polling and artwork; not an installer setting.')
    parser.add_argument('--enable-feedback', action='store_true')
    parser.add_argument('--output', default='releases/is-the-mountain-out.zip')
    args = parser.parse_args()
    try:
        output = build_package(args.output, args.service_url, args.enable_feedback)
    except ValueError as error:
        parser.error(str(error))
    print(output)


if __name__ == '__main__':
    main()
