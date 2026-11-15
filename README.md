# byro.info

Website of [byro](https://github.com/byro/byro), a free membership
administration for clubs and associations. It introduces byro in German and
English and links to the [documentation](https://byro.readthedocs.io/) and the
source code.

The pages are static HTML. `build.py` renders the Jinja2 templates in
`templates/` into `build/`, and `check.py` looks for broken links and missing
metadata. Texts live in `content/de.toml` and `content/en.toml`; links and the
demo login live in `config.toml`. The demo page only appears once `demo.url` is
set.

Pushes to `main` are published to GitHub Pages by
`.github/workflows/pages.yml`. Pull requests are only built and checked.

The screenshots show byro v2026.4.0 with its test data. The byro logo is by
Markus Kempken, the font is Inter (OFL) and the icons are from Lucide (ISC).
