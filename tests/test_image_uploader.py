import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.image_uploader import image_uploader


def test_guess_upload_filename_adds_extension_from_content_type():
    image_data = b"\x89PNG\r\n\x1a\nrest"

    filename = image_uploader._guess_upload_filename(
        "https://example.com/path/no-extension",
        "Demo Image",
        "image/png",
        image_data,
    )

    assert filename == "Demo_Image.png"


def test_guess_upload_filename_keeps_existing_extension():
    image_data = b"\xff\xd8\xff\xe0\x00\x10JF"

    filename = image_uploader._guess_upload_filename(
        "https://example.com/path/photo.jpeg",
        "",
        "image/jpeg",
        image_data,
    )

    assert filename == "photo.jpeg"
