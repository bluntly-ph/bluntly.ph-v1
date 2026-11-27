"""Image fingerprints for duplicate review photos (QA, 2026-09-29): pure.

Layer 1 of image plagiarism, and the one that needs no outside provider:
compare a review's photo with every other review's photo on this platform.

* **Exact copy**: SHA-256 of the uploaded bytes.
* **Near copy** (resized, recompressed, re-saved, lightly cropped or tinted):
  a 64-bit difference hash (dHash). The image is decoded, EXIF-rotated,
  flattened to greyscale and shrunk to 9 x 8; each bit says whether a pixel is
  brighter than its right-hand neighbour. Re-encoding barely moves those
  gradients, so two copies differ in a few bits while unrelated photos differ
  in about half of them. `NEAR_DISTANCE` is the flag threshold, in bits of
  Hamming distance.

A match is moderation evidence only. It never blocks an upload or a review,
never removes anything, and is shown to no one but staff: two honest buyers
can photograph the same box against the same white wall.

Decoding is also where a corrupt file is refused. The upload route already
sniffs magic bytes; a file whose header says JPEG but whose body does not
decode, or whose dimensions claim a decompression bomb, is rejected here with
a plain message instead of being stored.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

ALGORITHM_VERSION = "dhash64-v1"
HASH_BITS = 64
#: At most this many differing bits counts as the same picture. Measured on a
#: synthetic corpus (tests/test_duplicate_images.py): halved in size, JPEG
#: quality 30, PNG re-save and 25% brighter all 0 bits; a 10% crop 11 bits;
#: forty unrelated photos 23 to 41 bits. Configurable here; documented in
#: docs/ANTI_FARMING_AND_PLAGIARISM.md.
NEAR_DISTANCE = 12
#: A photo larger than this many pixels is refused before it is decoded
#: (Pillow's own guard is 89 megapixels; a phone photo is about 12).
MAX_PIXELS = 50_000_000


class UnreadableImage(ValueError):
    """The bytes are not an image this service can decode safely."""


@dataclass(frozen=True)
class Fingerprint:
    sha256: str
    dhash: int          # unsigned 64-bit
    width: int
    height: int

    @property
    def dhash_signed(self) -> int:
        """The same 64 bits as a signed BIGINT, for Postgres."""
        return self.dhash - (1 << 64) if self.dhash >= (1 << 63) else self.dhash


def from_signed(value: int) -> int:
    return value + (1 << 64) if value < 0 else value


def distance(a: int, b: int) -> int:
    """Hamming distance between two 64-bit hashes (signed or unsigned)."""
    return bin((from_signed(a) ^ from_signed(b)) & ((1 << 64) - 1)).count("1")


def fingerprint(data: bytes) -> Fingerprint:
    """Decode safely and fingerprint. Raises `UnreadableImage`."""
    try:
        with Image.open(io.BytesIO(data)) as probe:
            width, height = probe.size
            if width <= 0 or height <= 0 or width * height > MAX_PIXELS:
                raise UnreadableImage("That photo is too large to process.")
            probe.verify()                      # structure check, no pixels yet
        with Image.open(io.BytesIO(data)) as img:
            img.load()                          # the full decode: corrupt bodies fail here
            upright = ImageOps.exif_transpose(img)
            small = upright.convert("L").resize((9, 8), Image.Resampling.LANCZOS)
            pixels = list(small.getdata())
    except UnreadableImage:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError,
            Image.DecompressionBombError) as exc:
        raise UnreadableImage("That file could not be read as an image.") from exc
    bits = 0
    for row in range(8):
        for col in range(8):
            left = pixels[row * 9 + col]
            right = pixels[row * 9 + col + 1]
            bits = (bits << 1) | (1 if left > right else 0)
    return Fingerprint(sha256=hashlib.sha256(data).hexdigest(), dhash=bits,
                       width=width, height=height)
