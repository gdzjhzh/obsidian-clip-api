import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.services.markdown_converter import markdown_converter


def test_merge_wechat_images_replaces_empty_placeholders_and_appends_missing():
    markdown = "# Title\n\n![]()\n\nParagraph\n\n![]()\n"
    wechat_images = [
        ("https://example.com/a.jpg", ""),
        ("https://example.com/b.jpg", ""),
        ("https://example.com/c.jpg", ""),
    ]

    result = markdown_converter._merge_wechat_images_into_markdown(markdown, wechat_images)

    assert "![]()" not in result
    assert "https://example.com/a.jpg" in result
    assert "https://example.com/b.jpg" in result
    assert "https://example.com/c.jpg" in result


def test_convert_keeps_wechat_images_when_html_contains_empty_img_tags():
    html = """
    <html>
      <body>
        <script>
          var picture_page_info_list = [
            {width: 100, cdn_url: 'https://example.com/body-1.png'},
            {width: 100, cdn_url: 'https://example.com/body-2.png'}
          ].slice(0);
        </script>
        <h1>Article</h1>
        <p>Intro</p>
        <img src="">
      </body>
    </html>
    """

    markdown, images = markdown_converter.convert(html)

    assert ("https://example.com/body-1.png", "") in images
    assert ("https://example.com/body-2.png", "") in images
    assert "https://example.com/body-1.png" in markdown
    assert "https://example.com/body-2.png" in markdown
    assert "![]()" not in markdown
