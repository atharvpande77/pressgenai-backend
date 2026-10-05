import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.stories import service, utils


def run(coro):
    return asyncio.run(coro)


def test_english_title_used_without_llm_call(monkeypatch):
    translate = AsyncMock()
    monkeypatch.setattr(utils, "translate_title_to_english", translate)
    assert run(utils.ensure_english_title("Road repair begins in Nagpur", None)) == "Road repair begins in Nagpur"
    translate.assert_not_called()


def test_generated_english_title_preferred(monkeypatch):
    translate = AsyncMock()
    monkeypatch.setattr(utils, "translate_title_to_english", translate)
    assert run(utils.ensure_english_title("नागपुरात रस्ता दुरुस्ती", "Road repair in Nagpur")) == "Road repair in Nagpur"
    translate.assert_not_called()


@pytest.mark.parametrize("english_title", [None, "", "नागपुर रस्ता"])
def test_non_english_title_is_translated(monkeypatch, english_title):
    translate = AsyncMock(return_value="Road repair in Nagpur")
    monkeypatch.setattr(utils, "translate_title_to_english", translate)
    assert run(utils.ensure_english_title("नागपुरात रस्ता दुरुस्ती", english_title)) == "Road repair in Nagpur"
    translate.assert_awaited_once()


def test_translation_failure_raises(monkeypatch):
    monkeypatch.setattr(utils, "translate_title_to_english", AsyncMock(return_value=None))
    with pytest.raises(ValueError):
        run(utils.ensure_english_title("नागपुरात रस्ता दुरुस्ती", None))


def test_unique_slug_retries_with_longer_suffix():
    session = MagicMock()
    found = MagicMock()
    found.scalar_one_or_none.return_value = object()
    free = MagicMock()
    free.scalar_one_or_none.return_value = None
    # 5 short-suffix collisions, then a free slug
    session.execute = AsyncMock(side_effect=[found] * 5 + [free])
    slug = run(service.generate_unique_slug(session, "Road repair in Nagpur"))
    base, suffix = slug.rsplit("-", 1)
    assert base == "road-repair-in-nagpur" and len(suffix) == 12


def test_unique_slug_raises_instead_of_returning_none():
    session = MagicMock()
    found = MagicMock()
    found.scalar_one_or_none.return_value = object()
    session.execute = AsyncMock(return_value=found)
    with pytest.raises(RuntimeError):
        run(service.generate_unique_slug(session, "Road repair"))
