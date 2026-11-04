from django.forms import Textarea

# CodeMirror 5 + js-beautify vendored under static/admin/vendor (no CDN).
_CM = "admin/vendor/codemirror"


class HtmlSourceWidget(Textarea):
    def __init__(self, attrs=None):
        default = {"rows": 8, "cols": 160, "class": "article-html-source"}
        if attrs:
            extra_class = attrs.get("class", "")
            merged = {**default, **attrs}
            merged["class"] = f"{default['class']} {extra_class}".strip()
            attrs = merged
        else:
            attrs = default
        super().__init__(attrs=attrs)

    class Media:
        css = {
            "all": (
                f"{_CM}/codemirror.min.css",
                "admin/css/article_html_editor.css",
            )
        }
        js = (
            f"{_CM}/codemirror.min.js",
            f"{_CM}/mode/xml/xml.min.js",
            f"{_CM}/mode/javascript/javascript.min.js",
            f"{_CM}/mode/css/css.min.js",
            f"{_CM}/mode/htmlmixed/htmlmixed.min.js",
            "admin/vendor/js-beautify/beautify-html.min.js",
            "admin/js/article_html_editor.js",
        )
