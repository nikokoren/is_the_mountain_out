# Follow-up on Termy review 522027

## Mount Hood polling

The repository source and the previous committed ZIP both decode to this valid
Liquid condition:

```liquid
{% if mountain == 'hood' %}
```

The previous export used YAML's single-quoted scalar style. In that style,
`''` encodes one literal quote; it is not an additional quote passed to Liquid.
For example:

```yaml
polling_url: '{% if mountain == ''hood'' %}portland{% endif %}'
```

After YAML parsing, the value is `{% if mountain == 'hood' %}portland{% endif %}`.
The original exported polling value exactly equals the source value. Rendering
it with `mountain=hood`, a saved `rainier_viewpoint=paradise` and
`hood_viewpoint=portland` produces `mountain=hood&viewpoint=portland&feedback=false`.
Rendering with no custom fields produces Rainier/Seattle with feedback disabled.

The author subsequently pasted the actual polling field from recipe 522027.
It does contain literal `''hood''`, `''rainier''`, `''portland''`, `''seattle''`
and `''false''`. Termy's diagnosis is correct for the installed recipe. The
repository and YAML round trip are correct, but the serialization escapes have
been retained in the installed field. Whether that happened during import or
manual copying is not established.

Replace the complete polling field with this single line, then save and use
TRMNL's Parse/refresh action:

```text
https://is-the-mountain-out.5g5wqr7kzx-466.workers.dev/api/visibility?mountain={{ mountain | default: 'rainier' }}&viewpoint={% if mountain == 'hood' %}{{ hood_viewpoint | default: 'portland' }}{% else %}{{ rainier_viewpoint | default: 'seattle' }}{% endif %}&feedback={{ show_feedback_qr | default: 'false' }}
```

The packager now exports the polling value in double-quoted YAML on one line,
matching the source style, so literal Liquid quotes remain easy to read and copy.
A regression test checks the serialized form, YAML round trip and Hood selection
from the exported archive.

## Full-layout verdict in X portrait

This finding is confirmed. With the native Framework 3.4.0 CSS, JS and fonts, the
96px verdict extends behind the opaque QR region. The text still exists in the
DOM and fits inside the overall view, so the old bounds/text checks passed while
the final characters were visually hidden. Adding
`lg:portrait:value--xlarge` reduces the base font to 74px and keeps the complete
verdict clear of the QR on X portrait. The stronger overlap check also found a
problem on OG portrait, where a font-size class for X alone cannot help.

The padded outer container now wraps a separate native flex container. This
lets Framework text fitting measure the true content width after reserving the
QR gutters, rather than the entire padded width. The correction uses native
Framework classes and its text-fitting engine; it adds no custom CSS or JavaScript.

[Before](termy-review/before.png) · [Fixed](termy-review/fixed.png)

These are local illustrative fixtures, not hosted TRMNL screenshots or live data.
The browser suite now compares the actual verdict glyph range against the QR
rectangle to catch this type of overlap across the supported device matrix.

## Whitespace

This observation is also confirmed, particularly in tall half-vertical layouts.
Centering content moves the whitespace but does not reduce it. Adding a viewpoint
name would change the deliberately minimal mountain-and-verdict design, so this
review does not add text or claim that the layout-density feedback is resolved.
See the [layout review sheet](publishing-layouts.png).
