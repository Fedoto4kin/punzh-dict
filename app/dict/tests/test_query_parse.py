from unittest.mock import patch

from django.test import TestCase

from dict.ai import query_parse as qp
from dict.models import Article, SemanticField, Tag


class NormalizeParsedTestCase(TestCase):
    def setUp(self):
        self.field_defs = {
            "Животный мир": "животные",
            "Речь и звуки": "речь",
        }
        self.allowed_tags = ["бран.", "неодобр.", "всг.", "примета", "v", "s"]
        self.allowed_dialects = {"всг.": "весьегонский", "толм.": "толмачевский"}
        self.tag_aliases = {
            "бран.": "бран.",
            "примета": "примета",
            "глагол": "v",
            "глаголы": "v",
            "v": "v",
            "verbum, глагол": "v",
            "союз": "conj",
            "предлог": "prep",
            "прилагательное": "a",
            "существительное": "s",
            "conj": "conj",
            "prep": "prep",
            "a": "a",
            "s": "s",
        }
        self.tag_names = {
            "v": "verbum, глагол",
            "s": "substantivum, имя существительное",
            "примета": "примета",
            "бран.": "бранное",
        }

    def test_keeps_known_axes(self):
        payload = qp._normalize_parsed(
            {
                "lexical": ["коза", "разведение"],
                "focus": ["коза"],
                "related": ["коза", "доить", "загон", "нож"],
                "fields": ["Животный мир"],
                "tags": ["бран."],
                "dialect": "всг.",
                "dropped": ["найди"],
                "display": "искали: коза",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertEqual(payload["lexical"], ["коза", "разведение"])
        self.assertEqual(payload["focus"], ["коза"])
        # related drops duplicates of lexical and focus
        self.assertEqual(payload["related"], ["доить", "загон", "нож"])
        self.assertEqual(payload["fields"], ["Животный мир"])
        self.assertEqual(payload["tags"], ["бран."])
        self.assertEqual(payload["dialect"], "всг.")
        self.assertTrue(payload["parse_ok"])
        self.assertEqual(payload["warnings"], [])

    def test_focus_alone_parse_ok(self):
        payload = qp._normalize_parsed(
            {
                "lexical": [],
                "focus": ["нож"],
                "related": ["нож", "лезвие"],
                "fields": [],
                "tags": [],
                "dialect": None,
                "dropped": [],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertTrue(payload["parse_ok"])
        self.assertEqual(payload["focus"], ["нож"])
        self.assertEqual(payload["related"], ["лезвие"])
        # focus is ranking-only — not echoed in axes_display
        self.assertNotIn("ответ:", (payload.get("axes_display") or "").lower())
        self.assertNotIn("нож", payload.get("axes_display") or "")

    def test_promote_pos_and_priemeta_into_tags(self):
        """«глаголы в приметах» free axes → tags примета + v."""
        Tag.objects.create(tag="примета", name="примета", type=3, sorting=20)
        Tag.objects.create(tag="v", name="verbum, глагол", type=2, level=0, sorting=1)
        payload = qp._normalize_parsed(
            {
                "lexical": ["глагол"],
                "focus": ["глагол"],
                "related": ["примета"],
                "fields": ["Речь и звуки"],
                "tags": [],
                "dialect": None,
                "dropped": ["найди"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_alias_map=self.tag_aliases,
            tag_names=self.tag_names,
            query="найди глаголы в приметах",
        )
        self.assertEqual(sorted(payload["tags"]), ["v", "примета"])
        self.assertEqual(payload["lexical"], [])
        self.assertEqual(payload["focus"], [])
        self.assertEqual(payload["related"], [])
        self.assertIn("пометы:", payload["axes_display"])
        self.assertIn("verbum, глагол", payload["axes_display"])
        self.assertIn("примета", payload["axes_display"])

    def test_dropped_does_not_repeat_lexical(self):
        """LLM may put «три» in lexical and dropped — keep axis, clear dropped."""
        payload = qp._normalize_parsed(
            {
                "lexical": ["один", "два", "три"],
                "focus": [],
                "related": [],
                "fields": [],
                "tags": [],
                "dialect": None,
                "dropped": ["три"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            query="один два три",
        )
        self.assertEqual(payload["lexical"], ["один", "два", "три"])
        self.assertEqual(payload["dropped"], [])
        self.assertNotIn("пропущено", payload["axes_display"])

    def test_dialect_meta_lemmas_stripped_from_lexical(self):
        """«весьегонский говор» → dialect only; не lexical «весьегонский»."""
        payload = qp._normalize_parsed(
            {
                "lexical": ["весьегонский"],
                "focus": [],
                "related": [],
                "fields": [],
                "tags": [],
                "dialect": "всг.",
                "dropped": ["говор"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            query="весьегонский говор",
        )
        self.assertEqual(payload["dialect"], "всг.")
        self.assertEqual(payload["lexical"], [])
        self.assertIn("говор:", payload["axes_display"])

    def test_related_pos_words_stripped_not_theme(self):
        """Союз/предлог/… must not stay in related («рядом по теме»)."""
        self.allowed_tags = list(self.allowed_tags) + [
            "conj",
            "prep",
            "a",
            "s",
            "v",
            "примета",
        ]
        payload = qp._normalize_parsed(
            {
                "lexical": [],
                "focus": [],
                "related": [
                    "союз",
                    "предлог",
                    "прилагательное",
                    "существительное",
                ],
                "fields": [],
                "tags": ["примета", "v"],
                "dialect": None,
                "dropped": [],
                "display": "глаголы в приметах",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_alias_map=self.tag_aliases,
            query="глаголы в приметах",
        )
        self.assertEqual(payload["related"], [])
        self.assertEqual(sorted(payload["tags"]), ["v", "примета"])
        self.assertNotIn("союз", payload["axes_display"])
        self.assertEqual(payload["display"], "глаголы в приметах")

    def test_mark_query_drops_semantic_related(self):
        """Пометы → только tags; смысловой related от пометы отбрасываем."""
        Tag.objects.create(tag="примета", name="примета", type=3, sorting=20)
        payload = qp._normalize_parsed(
            {
                "lexical": [],
                "focus": [],
                "related": ["суеверие", "знак", "погода", "примета"],
                "fields": ["Речь и звуки"],
                "tags": ["примета"],
                "dialect": None,
                "dropped": ["найди"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_alias_map=self.tag_aliases,
            tag_names=self.tag_names,
            query="слова в приметах",
        )
        self.assertEqual(payload["tags"], ["примета"])
        self.assertEqual(payload["related"], [])
        self.assertEqual(payload["fields"], [])
        self.assertEqual(payload["lexical"], [])

    def test_invented_stylistic_tag_becomes_soft(self):
        """«как варили пиво» → с.-х. soft (rank only), not hard AND."""
        Tag.objects.create(tag="с.-х.", name="сельское хозяйство", type=3, sorting=30)
        self.field_defs = {
            **self.field_defs,
            "Пища и напитки": "еда",
            "Сельское хозяйство": "сх",
        }
        self.allowed_tags = list(self.allowed_tags) + ["с.-х."]
        aliases = {
            **self.tag_aliases,
            "с.-х.": "с.-х.",
            "сельское хозяйство": "с.-х.",
            "сельхоз": "с.-х.",
        }
        names = {**self.tag_names, "с.-х.": "сельское хозяйство"}
        payload = qp._normalize_parsed(
            {
                "lexical": ["варить", "пиво"],
                "focus": [],
                "related": ["утварь"],
                "fields": ["Пища и напитки", "Сельское хозяйство"],
                "tags": ["с.-х."],
                "dialect": None,
                "dropped": ["как"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_alias_map=aliases,
            tag_names=names,
            query="как варили пиво",
        )
        self.assertEqual(payload["tags"], [])
        self.assertEqual(payload["tags_soft"], ["с.-х."])
        self.assertEqual(payload["lexical"], ["варить", "пиво"])
        self.assertIn("Пища и напитки", payload["fields"])
        self.assertIn("учли пометы", payload["axes_display"])

    def test_keeps_stylistic_tag_named_in_query(self):
        Tag.objects.create(tag="с.-х.", name="сельское хозяйство", type=3, sorting=30)
        self.allowed_tags = list(self.allowed_tags) + ["с.-х."]
        aliases = {
            **self.tag_aliases,
            "с.-х.": "с.-х.",
            "сельское хозяйство": "с.-х.",
        }
        names = {**self.tag_names, "с.-х.": "сельское хозяйство"}
        payload = qp._normalize_parsed(
            {
                "lexical": [],
                "focus": [],
                "related": [],
                "fields": [],
                "tags": ["с.-х."],
                "dialect": None,
                "dropped": ["слова"],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_alias_map=aliases,
            tag_names=names,
            query="сельскохозяйственные термины с.-х.",
        )
        self.assertEqual(payload["tags"], ["с.-х."])

    def test_drops_unknown_field_and_tag(self):
        payload = qp._normalize_parsed(
            {
                "lexical": ["х"],
                "fields": ["Выдуманное поле", "Животный мир"],
                "tags": ["xyz.", "бран."],
                "dialect": None,
                "dropped": [],
                "display": "",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertEqual(payload["fields"], ["Животный мир"])
        self.assertEqual(payload["tags"], ["бран."])
        self.assertTrue(any("unknown field" in w for w in payload["warnings"]))
        self.assertTrue(any("unknown tag" in w for w in payload["warnings"]))

    def test_dialect_by_name_and_unknown(self):
        ok = qp._normalize_parsed(
            {"lexical": ["a"], "fields": [], "tags": [], "dialect": "Весьегонский"},
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertEqual(ok["dialect"], "всг.")

        bad = qp._normalize_parsed(
            {"lexical": ["a"], "fields": [], "tags": [], "dialect": "питерский"},
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertIsNone(bad["dialect"])
        self.assertTrue(any("unknown dialect" in w for w in bad["warnings"]))

    def test_clips_long_llm_display(self):
        payload = qp._normalize_parsed(
            {
                "lexical": ["коза"],
                "fields": [],
                "tags": [],
                "dialect": None,
                "dropped": ["найди"],
                "display": "x" * (qp.MAX_DISPLAY_LEN + 50),
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertLessEqual(len(payload["display"]), qp.MAX_DISPLAY_LEN)
        self.assertTrue(payload["display"].startswith("x"))
        self.assertTrue(any("display too long" in w for w in payload["warnings"]))

    def test_keeps_llm_display_and_axes(self):
        payload = qp._normalize_parsed(
            {
                "lexical": ["варить", "пиво"],
                "fields": ["Пища и напитки"],
                "tags": ["v"],
                "dialect": None,
                "dropped": ["как"],
                "display": "Ищем глаголы про варку пива",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
            tag_names=self.tag_names,
            query="глаголы про то как варить пиво",
        )
        self.assertEqual(payload["display"], "Ищем глаголы про варку пива")
        self.assertIn("варить", payload["axes_display"])
        self.assertIn("пометы:", payload["axes_display"])
        self.assertIn("пропущено", payload["axes_display"])

    def test_empty_llm_display_still_has_axes(self):
        payload = qp._normalize_parsed(
            {
                "lexical": ["коза"],
                "fields": [],
                "tags": [],
                "dialect": None,
                "dropped": ["найди"],
                "display": "  ",
            },
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertEqual(payload["display"], "")
        self.assertIn("коза", payload["axes_display"])
        self.assertIn("пропущено", payload["axes_display"])

    def test_caps_list_length(self):
        many = [f"лемма{i}" for i in range(qp.MAX_LIST_ITEMS + 5)]
        payload = qp._normalize_parsed(
            {"lexical": many, "fields": [], "tags": [], "dialect": None},
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertEqual(len(payload["lexical"]), qp.MAX_LIST_ITEMS)

    def test_empty_axes_parse_ok_false(self):
        payload = qp._normalize_parsed(
            {"lexical": [], "fields": [], "tags": [], "dialect": None},
            self.field_defs,
            self.allowed_tags,
            self.allowed_dialects,
        )
        self.assertFalse(payload["parse_ok"])


class ParseQueryTestCase(TestCase):
    def setUp(self):
        SemanticField.objects.create(
            name="Животный мир", definition="животные", sorting=1
        )
        Tag.objects.create(tag="бран.", name="бранное", type=3, sorting=1)
        Tag.objects.create(tag="всг.", name="весьегонский", type=4, sorting=1)

    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_parse_ok_path(self, mock_chat):
        mock_chat.return_value = {
            "lexical": ["коза"],
            "fields": ["Животный мир"],
            "tags": [],
            "dialect": None,
            "dropped": ["найди"],
            "display": "искали: коза; «найди» пропущено",
        }
        result = qp.parse_query("Найди слова про коз")
        self.assertTrue(result["ok"])
        self.assertTrue(result["parse_ok"])
        self.assertEqual(result["lexical"], ["коза"])
        self.assertEqual(result["fields"], ["Животный мир"])
        self.assertIsNone(result["error"])
        mock_chat.assert_called_once()

    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_llm_unavailable(self, mock_chat):
        mock_chat.return_value = None
        result = qp.parse_query("коза")
        self.assertFalse(result["ok"])
        self.assertFalse(result["parse_ok"])
        self.assertEqual(result["error"], "llm_unavailable")

    def test_empty_query(self):
        result = qp.parse_query("   ")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "empty_query")

    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_truncates_long_query(self, mock_chat):
        mock_chat.return_value = {
            "lexical": ["x"],
            "fields": [],
            "tags": [],
            "dialect": None,
            "dropped": [],
            "display": "",
        }
        long_q = "а" * (qp.MAX_QUERY_LEN + 40)
        result = qp.parse_query(long_q)
        self.assertTrue(result["ok"])
        self.assertEqual(len(result["query"]), qp.MAX_QUERY_LEN)
        self.assertIn("query truncated", result["warnings"])
        user_prompt = mock_chat.call_args[0][1]
        self.assertLessEqual(len(user_prompt), len(long_q) + 5000)

    def test_looks_like_krl_query(self):
        self.assertTrue(qp.looks_like_krl_query("kazi"))
        self.assertTrue(qp.looks_like_krl_query("käz’i"))
        self.assertFalse(qp.looks_like_krl_query("кошка"))
        self.assertFalse(qp.looks_like_krl_query("слова про kazi"))
        self.assertFalse(qp.looks_like_krl_query(""))

    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_kazi_skips_llm_when_in_index(self, mock_chat):
        """kazi (cat) must not go to LLM → false friend käzi/hand."""
        Article.objects.create(
            word="kaz’i, ~n’e",
            article_html="<b>kaz’i</b> кошка",
        )
        result = qp.parse_query("kazi")
        mock_chat.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertTrue(result["parse_ok"])
        self.assertTrue(result["krl_headword"])
        self.assertEqual(result["fields"], [])
        self.assertEqual(result["related"], [])
        self.assertEqual(result["lexical"], [])
        self.assertIn("карельское", result["display"])

    @patch("dict.ai.query_parse.ai_client.chat_json")
    def test_latin_miss_skips_llm(self, mock_chat):
        result = qp.parse_query("xyzzyqq")
        mock_chat.assert_not_called()
        self.assertTrue(result["ok"])
        self.assertFalse(result["parse_ok"])
        self.assertFalse(result["krl_headword"])
