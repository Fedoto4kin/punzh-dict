"""Django middleware for the dict app."""

from django.contrib import messages

from dict.ai.classify_bg import (
    format_classify_notice_message,
    pop_classify_notices,
)


class OntologyClassifyNoticeMiddleware:
    """
    On each /admin/ request, flush background classify notices into
    django.contrib.messages (visible after navigation or F5).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        self._flush_notices(request)
        return self.get_response(request)

    def _flush_notices(self, request):
        user = getattr(request, "user", None)
        if user is None or not user.is_authenticated:
            return
        path = getattr(request, "path", "") or ""
        if not path.startswith("/admin/"):
            return
        for notice in pop_classify_notices(user.pk):
            text = format_classify_notice_message(notice)
            if notice.get("ok"):
                messages.info(request, text)
            else:
                messages.warning(request, text)
