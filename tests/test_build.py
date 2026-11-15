import copy
import re
import tempfile
import unittest
from pathlib import Path

import build
import check

DEMO = {
    "url": "https://demo.byro.info",
    "username": "demo-user",
    "password": "demo-password",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class BuildTestCase(unittest.TestCase):
    site_url = "https://byro.info"
    demo = None

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls._tmp.name)
        config = copy.deepcopy(build.load_config())
        config["site"]["url"] = cls.site_url
        if cls.demo:
            config["demo"].update(cls.demo)
        build.build(config, cls.out)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def all_html(self) -> str:
        return "".join(read(p) for p in self.out.rglob("*.html"))


class DefaultBuildTest(BuildTestCase):
    def test_language_pages_have_lang_and_canonical(self):
        for path, lang, canonical in [
            ("index.html", "de", "https://byro.info/"),
            ("de/index.html", "de", "https://byro.info/de/"),
            ("en/index.html", "en", "https://byro.info/en/"),
        ]:
            html = read(self.out / path)
            self.assertIn(f'<html lang="{lang}"', html, path)
            self.assertIn(f'<link rel="canonical" href="{canonical}">', html, path)

    def test_home_pages_reference_each_other_with_hreflang(self):
        for path in ["index.html", "de/index.html", "en/index.html"]:
            html = read(self.out / path)
            self.assertIn('<link rel="alternate" hreflang="de" href="https://byro.info/de/">', html)
            self.assertIn('<link rel="alternate" hreflang="en" href="https://byro.info/en/">', html)
            self.assertIn('<link rel="alternate" hreflang="x-default" href="https://byro.info/">', html)

    def test_titles_and_descriptions_differ_per_language(self):
        de, en = read(self.out / "de/index.html"), read(self.out / "en/index.html")
        title = re.compile(r"<title>(.+?)</title>")
        description = re.compile(r'<meta name="description" content="(.+?)">')
        self.assertNotEqual(title.search(de)[1], title.search(en)[1])
        self.assertNotEqual(description.search(de)[1], description.search(en)[1])

    def test_docs_links_match_page_language(self):
        de, en = read(self.out / "de/index.html"), read(self.out / "en/index.html")
        self.assertIn("https://byro.readthedocs.io/de/latest/", de)
        self.assertNotIn("https://byro.readthedocs.io/en/", de)
        self.assertIn("https://byro.readthedocs.io/en/latest/", en)
        self.assertNotIn("https://byro.readthedocs.io/de/", en)

    def test_root_links_to_both_languages_without_javascript(self):
        html = read(self.out / "index.html")
        self.assertIn('href="/de/"', html)
        self.assertIn('href="/en/"', html)

    def test_only_root_page_redirects_by_browser_language(self):
        self.assertIn("navigator.languages", read(self.out / "index.html"))
        for path in ["de/index.html", "en/index.html"]:
            self.assertNotIn("navigator.languages", read(self.out / path))

    def test_demo_is_hidden_without_url(self):
        self.assertFalse((self.out / "de/demo").exists())
        self.assertFalse((self.out / "en/demo").exists())
        self.assertNotIn("/demo/", self.all_html())
        self.assertNotIn("demo", read(self.out / "sitemap.xml"))

    def test_sitemap_lists_public_pages(self):
        locs = re.findall(r"<loc>(.+?)</loc>", read(self.out / "sitemap.xml"))
        self.assertEqual(
            locs, ["https://byro.info/", "https://byro.info/de/", "https://byro.info/en/"]
        )

    def test_robots_points_to_sitemap(self):
        robots = read(self.out / "robots.txt")
        self.assertIn("Sitemap: https://byro.info/sitemap.xml", robots)

    def test_open_graph_image_is_absolute(self):
        html = read(self.out / "de/index.html")
        match = re.search(r'<meta property="og:image" content="(.+?)">', html)
        self.assertTrue(match[1].startswith("https://byro.info/"))
        self.assertTrue((self.out / match[1].removeprefix("https://byro.info/")).is_file())

    def test_site_passes_checks(self):
        self.assertEqual(check.check_site(self.out, self.site_url), [])


class SubpathBuildTest(BuildTestCase):
    site_url = "https://byro.github.io/website"

    def test_urls_include_base_path(self):
        html = read(self.out / "de/index.html")
        self.assertIn('<link rel="canonical" href="https://byro.github.io/website/de/">', html)
        self.assertIn('href="/website/en/"', html)
        self.assertNotRegex(html, r'(href|src)="/(de|en|assets)/')

    def test_sitemap_and_robots_use_base_path(self):
        self.assertIn(
            "<loc>https://byro.github.io/website/en/</loc>", read(self.out / "sitemap.xml")
        )
        self.assertIn(
            "Sitemap: https://byro.github.io/website/sitemap.xml",
            read(self.out / "robots.txt"),
        )

    def test_site_passes_checks(self):
        self.assertEqual(check.check_site(self.out, self.site_url), [])


class DemoBuildTest(BuildTestCase):
    demo = DEMO

    def test_demo_pages_show_access_data(self):
        for lang in ["de", "en"]:
            html = read(self.out / lang / "demo/index.html")
            self.assertIn(f'<html lang="{lang}"', html)
            self.assertIn('href="https://demo.byro.info"', html)
            self.assertIn("demo-user", html)
            self.assertIn("demo-password", html)

    def test_home_pages_link_to_demo_page(self):
        self.assertIn('href="/de/demo/"', read(self.out / "de/index.html"))
        self.assertIn('href="/en/demo/"', read(self.out / "en/index.html"))

    def test_sitemap_lists_demo_pages(self):
        sitemap = read(self.out / "sitemap.xml")
        self.assertIn("<loc>https://byro.info/de/demo/</loc>", sitemap)
        self.assertIn("<loc>https://byro.info/en/demo/</loc>", sitemap)

    def test_site_passes_checks(self):
        self.assertEqual(check.check_site(self.out, self.site_url), [])


class CheckTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.out = Path(self._tmp.name)
        build.build(build.load_config(), self.out)

    def tearDown(self):
        self._tmp.cleanup()

    def test_reports_broken_internal_link(self):
        page = self.out / "en/index.html"
        page.write_text(read(page).replace('href="/de/"', 'href="/missing/"', 1))
        errors = check.check_site(self.out, "https://byro.info")
        self.assertTrue(any("/missing/" in error for error in errors), errors)

    def test_reports_external_script(self):
        page = self.out / "de/index.html"
        page.write_text(
            read(page).replace("</head>", '<script src="https://cdn.example.org/x.js"></script></head>')
        )
        errors = check.check_site(self.out, "https://byro.info")
        self.assertTrue(any("cdn.example.org" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
