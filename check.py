"""Check a built site: internal links and assets, page metadata, hreflang,
sitemap and robots.txt, and that no resources are loaded from other hosts.

Usage: python check.py [build-directory]

Uses SITE_URL like build.py, so the check matches the URL the site was built for.
"""

import os
import re
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlsplit

# (tag, attribute) pairs that make the browser load something.
RESOURCE_ATTRIBUTES = {
    ("script", "src"),
    ("img", "src"),
    ("img", "srcset"),
    ("source", "src"),
    ("source", "srcset"),
    ("iframe", "src"),
    ("video", "src"),
    ("audio", "src"),
}
# <link rel="..."> values whose href is fetched directly.
LOADING_LINK_RELS = {"stylesheet", "icon", "preload", "modulepreload", "apple-touch-icon", "manifest"}


class PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.lang = None
        self.title = ""
        self.in_title = False
        self.description = None
        self.noindex = False
        self.canonical = None
        self.alternates = {}
        self.ids = set()
        self.links = []  # (url, loads_resource)

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "html":
            self.lang = a.get("lang")
        elif tag == "title":
            self.in_title = True
        elif tag == "meta":
            name, prop = a.get("name"), a.get("property")
            if name == "description":
                self.description = a.get("content")
            elif name == "robots" and "noindex" in a.get("content", ""):
                self.noindex = True
            elif prop in ("og:image", "og:url"):
                self.links.append((a.get("content", ""), True))
        elif tag == "link":
            rel = set(a.get("rel", "").split())
            if "canonical" in rel:
                self.canonical = a.get("href")
            elif "alternate" in rel and "hreflang" in a:
                self.alternates[a["hreflang"]] = a.get("href")
            self.links.append((a.get("href", ""), bool(rel & LOADING_LINK_RELS)))
        elif tag == "a" and "href" in a:
            self.links.append((a["href"], False))
        for attr in ("src", "srcset"):
            if (tag, attr) in RESOURCE_ATTRIBUTES and attr in a:
                for candidate in a[attr].split(","):
                    self.links.append((candidate.split()[0], True))

    def handle_endtag(self, tag):
        if tag == "title":
            self.in_title = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data


def page_url(out: Path, file: Path, site_url: str) -> str:
    rel = file.relative_to(out).as_posix()
    if rel.endswith("index.html"):
        rel = rel.removesuffix("index.html")
    return f"{site_url}/{rel}"


def check_site(out: Path, site_url: str) -> list[str]:
    site_url = site_url.rstrip("/")
    base_path = urlsplit(site_url).path.rstrip("/")
    errors = []

    def resolve(path: str) -> Path | None:
        """Map a root-relative URL path to a file in the build, if it is ours."""
        if base_path and not (path == base_path or path.startswith(base_path + "/")):
            return None
        rel = path.removeprefix(base_path).lstrip("/")
        target = out / rel
        if rel == "" or rel.endswith("/"):
            target = target / "index.html"
        return target

    pages = {}
    ids = {}  # file -> element ids, for fragments of links between pages
    fragment_links = []  # (where, link, target file, fragment)
    for file in sorted(out.rglob("*.html")):
        parser = PageParser()
        parser.feed(file.read_text(encoding="utf-8"))
        pages[page_url(out, file, site_url)] = parser
        ids[file] = parser.ids
        where = file.relative_to(out).as_posix()

        if not parser.lang:
            errors.append(f"{where}: <html> has no lang attribute")
        if not parser.title.strip():
            errors.append(f"{where}: missing <title>")
        if not parser.noindex:
            if not parser.description:
                errors.append(f"{where}: missing meta description")
            if parser.canonical != page_url(out, file, site_url):
                errors.append(f"{where}: canonical is {parser.canonical!r}")

        for link, loads in parser.links:
            parts = urlsplit(link)
            if link.startswith("#"):
                if link[1:] not in parser.ids:
                    errors.append(f"{where}: no element with id for {link}")
                continue
            if link.startswith(site_url + "/") or link == site_url:
                path = urlsplit(link).path
            elif parts.scheme or link.startswith("//"):
                if loads:
                    errors.append(f"{where}: loads external resource {link}")
                continue
            elif link.startswith("/"):
                path = parts.path
            else:
                path = urlsplit(urljoin(page_url(out, file, site_url), link)).path
            target = resolve(path)
            if target is None:
                errors.append(f"{where}: {link} is outside the base path {base_path}")
            elif not target.is_file():
                errors.append(f"{where}: broken link {link}")
            elif parts.fragment and target.suffix == ".html":
                fragment_links.append((where, link, target, parts.fragment))

    for where, link, target, fragment in fragment_links:
        if fragment not in ids.get(target, set()):
            errors.append(f"{where}: no element with id for {link}")

    for url, parser in pages.items():
        for hreflang, target in parser.alternates.items():
            other = pages.get(target)
            if other is None:
                errors.append(f"{url}: hreflang {hreflang} points to unknown page {target}")
            elif other.alternates != parser.alternates:
                errors.append(f"{url}: hreflang links differ from those on {target}")

    sitemap = out / "sitemap.xml"
    locs = re.findall(r"<loc>(.+?)</loc>", sitemap.read_text()) if sitemap.is_file() else []
    indexable = sorted(url for url, parser in pages.items() if not parser.noindex)
    if sorted(locs) != indexable:
        errors.append(f"sitemap.xml lists {sorted(locs)}, indexable pages are {indexable}")

    robots = out / "robots.txt"
    if not robots.is_file() or f"Sitemap: {site_url}/sitemap.xml" not in robots.read_text():
        errors.append("robots.txt does not reference the sitemap")

    return errors


def main() -> None:
    import build

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else build.ROOT / "build"
    site_url = os.environ.get("SITE_URL") or build.load_config()["site"]["url"]
    errors = check_site(out, site_url)
    for error in errors:
        print(error)
    if errors:
        sys.exit(1)
    print(f"{out}: no problems found for {site_url}")


if __name__ == "__main__":
    main()
