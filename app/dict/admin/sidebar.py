"""Dict admin sidebar: model order + nested «Онтология» block."""

from django.contrib import admin

from .ontology import ontology_pending_count

# Sidebar under Dict: Слова, Переводы, then the rest (alpha).
# Semantic fields + pending queue are pulled into a nested «Онтология» block.
_DICT_MODEL_ORDER = {
    "article": 0,
    "articleindextranslate": 1,
}

_ONTOLOGY_SIDEBAR_MODELS = frozenset(
    {"semanticfield", "ontologyqueuearticle", "classificationsurveyresponse"}
)
_ONTOLOGY_SIDEBAR_ORDER = {
    "semanticfield": 0,
    "ontologyqueuearticle": 1,
    "classificationsurveyresponse": 2,
}


class DictSidebarAppList:
    """Build Django admin app_list with Dict + Ontology grouping."""

    def __call__(self, request):
        app_list = admin.AdminSite.get_app_list(admin.site, request)
        pending_n = ontology_pending_count()
        result = []
        for app in app_list:
            if app.get("app_label") != "dict":
                result.append(app)
                continue
            ontology_models = []
            dict_models = []
            for model in app["models"]:
                key = model["object_name"].lower()
                if key in _ONTOLOGY_SIDEBAR_MODELS:
                    if key == "ontologyqueuearticle":
                        # Badge = pending only; the changelist also has marked/skip.
                        model = {**model, "name": f"Разметка ({pending_n})"}
                    ontology_models.append(model)
                else:
                    dict_models.append(model)
            dict_models.sort(
                key=lambda m: (
                    _DICT_MODEL_ORDER.get(m["object_name"].lower(), 50),
                    m["name"].lower(),
                )
            )
            ontology_models.sort(
                key=lambda m: (
                    _ONTOLOGY_SIDEBAR_ORDER.get(m["object_name"].lower(), 50),
                    m["name"].lower(),
                )
            )
            app = {**app, "models": dict_models}
            result.append(app)
            if ontology_models:
                first_url = next(
                    (m.get("admin_url") for m in ontology_models if m.get("admin_url")),
                    app.get("app_url"),
                )
                result.append(
                    {
                        "name": "Онтология",
                        "app_label": "dict_ontology",
                        "app_url": first_url,
                        "has_module_perms": True,
                        "models": ontology_models,
                    }
                )
        return result


def install_dict_sidebar(site=None):
    site = site or admin.site
    site.get_app_list = DictSidebarAppList()
