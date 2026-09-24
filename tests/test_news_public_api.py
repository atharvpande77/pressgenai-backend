from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import bcrypt

from src.auth.utils import verify_pw
from src.news.schemas import ArticleListResponse, SitemapArticleResponse, _to_ist_iso
from src.news.service import slugify_city_name
from src.stories.utils import sluggify


def test_sluggify_keeps_devanagari_vowel_signs():
    title = "स्व. भानुताई गडकरी मेमोरियल डायग्नोस्टिक सेंटर येथे डायलिसीस सुविधेचा विस्तार"
    assert sluggify(title, max_words=10) == "स्व-भानुताई-गडकरी-मेमोरियल-डायग्नोस्टिक-सेंटर-येथे-डायलिसीस-सुविधेचा-विस्तार"


def test_sluggify_keeps_nukta_and_strips_punctuation():
    assert sluggify("गणेश चतुर्थी — उत्सव ज़ोरात!") == "गणेश-चतुर्थी-उत्सव-ज़ोरात"


def test_sluggify_latin_behaviour_unchanged():
    assert sluggify("Café Déjà vu: 2026 election!") == "cafe-deja-vu-2026-election"
    assert sluggify("Demand for safe footpaths on new Nasarla Road", max_words=10) == "demand-for-safe-footpaths-on-new-nasarla-road"


def test_city_slugs():
    assert slugify_city_name("Nagpur") == "nagpur"
    assert slugify_city_name("  Navi Mumbai ") == "navi-mumbai"


def test_naive_timestamps_are_published_as_ist():
    assert _to_ist_iso(datetime(2026, 9, 22, 18, 16, 43)) == "2026-09-22T18:16:43+05:30"
    assert _to_ist_iso(datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc)) == "2026-09-22T05:30:00+05:30"
    assert _to_ist_iso(None) is None


def _category(value):
    return SimpleNamespace(id=uuid4(), name=value.title(), value=value)


def test_primary_category_is_first_ordered_category():
    person = SimpleNamespace(id=uuid4(), first_name="A", last_name="B", username="@a", profile_image_key=None)
    article = SimpleNamespace(
        id=uuid4(), title="t", snippet="s", published_at=datetime(2026, 9, 22, 10), updated_at=None, slug="s-1",
        author=SimpleNamespace(user=person), editor=None, city_id=None, city=None,
        categories=[_category("culture"), _category("politics")], images_keys=[],
    )
    body = ArticleListResponse.model_validate(article).model_dump(mode="json")
    assert body["primary_category"]["value"] == "culture"
    assert body["published_at"].endswith("+05:30")

    sitemap = SitemapArticleResponse.model_validate(article).model_dump(mode="json")
    assert sitemap == {"slug": "s-1", "published_at": "2026-09-22T10:00:00+05:30", "updated_at": None,
                       "primary_category": body["primary_category"]}


def test_no_master_password():
    hashed = bcrypt.hashpw(b"correct horse", bcrypt.gensalt()).decode()
    assert verify_pw("correct horse", hashed)
    assert not verify_pw("pass1234", hashed)


def test_sitemap_row_without_slug_falls_back_to_id():
    article_id = uuid4()
    row = SimpleNamespace(id=article_id, slug=None, published_at=None, updated_at=None, categories=[])
    body = SitemapArticleResponse.model_validate(row).model_dump(mode="json")
    assert body["slug"] == str(article_id)
    assert body["primary_category"] is None
