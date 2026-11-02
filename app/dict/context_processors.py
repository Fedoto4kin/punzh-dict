from django.conf import settings


def classification_survey(request):
    return {
        "classification_survey_enabled": bool(
            getattr(settings, "CLASSIFICATION_SURVEY", False)
        ),
    }
