from PyQt6.QtGui import QImage

from src.gui.services.item_icons import ItemIconCache


def test_icon_cache_evicts_by_size_and_recency() -> None:
    image = QImage(1, 1, QImage.Format.Format_RGB32)
    cache = ItemIconCache(max_bytes=2 * image.sizeInBytes())
    cache._loaded(1, image)
    cache._loaded(2, image)
    assert cache.cached(1) is not None

    cache._loaded(3, image)

    assert cache.cached(2) is None
    assert cache.cached(1) is not None
    assert cache.cached(3) is not None


def test_oversized_icon_is_delivered_and_clears_cache() -> None:
    image = QImage(1, 1, QImage.Format.Format_RGB32)
    large = QImage(2, 2, QImage.Format.Format_RGB32)
    cache = ItemIconCache(max_bytes=image.sizeInBytes())
    delivered: list[int] = []
    cache.ready.connect(lambda icon_id, _: delivered.append(icon_id))
    cache._loaded(1, image)

    cache._loaded(2, large)

    assert delivered == [1, 2]
    assert cache.cached(1) is None
    assert cache.cached(2) is None
