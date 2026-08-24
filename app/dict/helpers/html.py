import re

_MULTI_SPACE = re.compile(r" {2,}")


def compact_article_html(html):
    """Drop indent/newlines/tabs from editor pretty-print; keep word spaces."""
    if not html:
        return html or ""
    lines = [line.strip() for line in html.replace("\t", " ").splitlines()]
    text = " ".join(line for line in lines if line)
    return _MULTI_SPACE.sub(" ", text).strip()
