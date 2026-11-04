"""
Django admin for dict — split by concern; import this package to register.

Public names used by tests: ArticleAdm, ArticleLinkReverseInline, TagAdm.
"""

from .article import ArticleAdm, SourceAdm  # noqa: F401
from .inlines import (  # noqa: F401
    ArticleAdditionInline,
    ArticleIndexTagInline,
    ArticleLinkInline,
    ArticleLinkReverseInline,
    ArticleSemanticFieldInline,
    TranslateInline,
)
from .ontology import (  # noqa: F401
    OntologyMarkupFilter,
    OntologyQueueAdm,
    SemanticFieldAdm,
    ontology_pending_count,
)
from .sidebar import install_dict_sidebar
from .survey import ClassificationSurveyResponseAdm  # noqa: F401
from .tags import TagAdm  # noqa: F401
from .translations import ArticleIndexTranslateAdm  # noqa: F401
from .widgets import HtmlSourceWidget  # noqa: F401

install_dict_sidebar()
