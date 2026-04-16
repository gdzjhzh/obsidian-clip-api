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


def test_clean_html_keeps_image_only_spans():
    html = """
    <html>
      <body>
        <figure>
          <span><img src="https://example.com/in-place.png" alt="inline image"/></span>
          <figcaption>Caption</figcaption>
        </figure>
      </body>
    </html>
    """

    cleaned = markdown_converter._clean_html(html)

    assert "https://example.com/in-place.png" in cleaned


def test_extract_wechat_images_supports_jsdecode_payloads():
    html = """
    <script>
      picture_page_info_list: [
        {cdn_url: JsDecode('https://example.com/1.png'), width: '100' * 1},
        {cdn_url: JsDecode('https://example.com/2.jpg'), width: '100' * 1}
      ],
    </script>
    """

    images = markdown_converter._extract_wechat_images(html)

    assert images == [
        ("https://example.com/1.png", ""),
        ("https://example.com/2.jpg", ""),
    ]


def test_convert_deduplicates_equivalent_image_urls_and_prefers_alt_text():
    html = """
    <html>
      <body>
        <script>
          picture_page_info_list: [
            {cdn_url: 'https://example.com/640.png?wx_fmt=png&amp;from=appmsg', width: 100}
          ],
        </script>
        <h1>Article</h1>
        <p>Intro</p>
        <figure>
          <span>
            <img
              src="https://example.com/640.png?wx_fmt=png&from=appmsg"
              alt="ExLink screenshot"
            />
          </span>
        </figure>
      </body>
    </html>
    """

    markdown, images = markdown_converter.convert(html)

    assert images == [("https://example.com/640.png?wx_fmt=png&from=appmsg", "ExLink screenshot")]
    assert markdown.count("https://example.com/640.png?wx_fmt=png&from=appmsg") == 1
