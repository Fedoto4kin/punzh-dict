from django.db.models import Func, Value
from django.db.models.expressions import BaseExpression


class Levenshtein(Func):
    """PostgreSQL fuzzystrmatch.levenshtein(a, b) with bound parameters."""

    function = "levenshtein"
    arity = 2

    def __init__(self, expression, search_term, **extras):
        if not isinstance(search_term, BaseExpression):
            search_term = Value(search_term)
        super().__init__(expression, search_term, **extras)
