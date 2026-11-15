"""Build the static byro website into a directory (default: build/).

Usage: python build.py [output-directory]

The environment variable SITE_URL overrides site.url from config.toml, for
example https://byro.github.io/website for a GitHub Pages project URL.
"""

import json
import os
import shutil
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

ROOT = Path(__file__).parent


@dataclass
class Page:
    template: str
    path: str  # relative to the site root, "" for the start page
    lang: str
    content_key: str
    # language -> path of the same page in that language, including the page
    # itself; "x-default" names the fallback for other languages
    alternates: dict[str, str] = field(default_factory=dict)
    in_sitemap: bool = True


def load_config() -> dict:
    with open(ROOT / "config.toml", "rb") as f:
        config = tomllib.load(f)
    config["content"] = {}
    for lang in config["site"]["languages"]:
        with open(ROOT / "content" / f"{lang}.toml", "rb") as f:
            config["content"][lang] = tomllib.load(f)
    return config


def site_pages(config: dict) -> list[Page]:
    languages = config["site"]["languages"]
    default = config["site"]["default_language"]

    home = {lang: f"{lang}/" for lang in languages} | {"x-default": ""}
    pages = [Page("root.html", "", default, "root", home)]
    pages += [Page("home.html", f"{lang}/", lang, "home", home) for lang in languages]

    if config["demo"]["url"]:
        demo = {lang: f"{lang}/demo/" for lang in languages}
        demo["x-default"] = demo[default]
        pages += [Page("demo.html", f"{lang}/demo/", lang, "demo", demo) for lang in languages]

    pages.append(Page("404.html", "404.html", default, "not_found", in_sitemap=False))
    return pages


def build(config: dict, out: Path) -> None:
    site_url = config["site"]["url"].rstrip("/")
    base_path = urlsplit(site_url).path.rstrip("/")
    pages = site_pages(config)

    def url(path: str) -> str:
        """Root-relative URL that includes the base path."""
        return f"{base_path}/{path}"

    def absolute_url(path: str) -> str:
        return f"{site_url}/{path}"

    def docs_url(lang: str, path: str = "") -> str:
        return config["links"]["docs"][lang] + path

    env = Environment(
        loader=FileSystemLoader(ROOT / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["html"] = Markup  # for trusted texts from content/*.toml
    env.globals.update(
        url=url,
        absolute_url=absolute_url,
        docs_url=docs_url,
        icon=lambda name: Markup((ROOT / "templates/icons" / f"{name}.svg").read_text().strip()),
        config=config,
        languages=config["site"]["languages"],
        default_language=config["site"]["default_language"],
    )

    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(ROOT / "static", out / "assets")

    for page in pages:
        t = config["content"][page.lang]
        context = {
            "page": page,
            "lang": page.lang,
            "t": t,
            "c": t["common"],
            "p": t[page.content_key],
            "all_content": config["content"],
            "demo": config["demo"],
            "structured_data": structured_data(page, config, absolute_url),
        }
        target = out / page.path
        if page.path.endswith("/") or page.path == "":
            target = target / "index.html"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(env.get_template(page.template).render(context), encoding="utf-8")

    sitemap_urls = [absolute_url(page.path) for page in pages if page.in_sitemap]
    (out / "sitemap.xml").write_text(
        env.get_template("sitemap.xml").render(urls=sitemap_urls), encoding="utf-8"
    )
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: {absolute_url('sitemap.xml')}\n", encoding="utf-8"
    )


def structured_data(page: Page, config: dict, absolute_url) -> Markup | None:
    """schema.org data for the home pages, limited to facts shown on the page."""
    if page.content_key != "home":
        return None
    data = {
        "@context": "https://schema.org",
        "@type": "SoftwareApplication",
        "name": "byro",
        "description": config["content"][page.lang]["home"]["description"],
        "url": absolute_url(page.path),
        "applicationCategory": "BusinessApplication",
        "license": "https://www.gnu.org/licenses/agpl-3.0.html",
        "isAccessibleForFree": True,
        "image": absolute_url("assets/img/byro-logo.svg"),
        "sameAs": [config["links"]["github"]],
        "softwareHelp": {"@type": "CreativeWork", "url": config["links"]["docs"][page.lang]},
    }
    # "</" must not end the surrounding <script> element early.
    return Markup(json.dumps(data, ensure_ascii=False).replace("</", "<\\/"))


def main() -> None:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "build"
    config = load_config()
    if os.environ.get("SITE_URL"):
        config["site"]["url"] = os.environ["SITE_URL"]
    build(config, out)
    print(f"Built {config['site']['url']} into {out}")


if __name__ == "__main__":
    main()
