from app.images import hamming_distance, sharpness_score
from tests.conftest import make_jpg


def test_hamming_distance_identical():
    assert hamming_distance("0" * 16, "0" * 16) == 0


def test_hamming_distance_different():
    # 0xff vs 0x00 -> 8 bits differ per byte.
    assert hamming_distance("ff" * 16, "00" * 16) == 128


def test_sharpness_score_flat_image_low():
    import io
    from PIL import Image

    buf = io.BytesIO()
    Image.new("L", (64, 64), 128).save(buf, "JPEG")
    assert sharpness_score(buf.getvalue()) < 5.0


def test_sharpness_score_noise_high():
    import io
    import random

    from PIL import Image

    random.seed(7)
    img = Image.new("L", (64, 64))
    img.putdata([random.randrange(0, 256) for _ in range(64 * 64)])
    buf = io.BytesIO()
    img.save(buf, "JPEG")
    assert sharpness_score(buf.getvalue()) > 5.0
