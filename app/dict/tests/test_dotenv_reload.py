import os
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from django.test import SimpleTestCase

from punzh.dotenv import dotenv_should_overwrite, watch_dotenv


class DotenvReloadTests(SimpleTestCase):
    def test_overwrite_only_in_runserver_worker(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("RUN_MAIN", None)
            self.assertFalse(dotenv_should_overwrite())
            os.environ["RUN_MAIN"] = "true"
            self.assertTrue(dotenv_should_overwrite())

    def test_watch_adds_existing_dotenv(self):
        sender = mock.Mock()
        sender.extra_files = set()
        with TemporaryDirectory() as tmp:
            dotenv = Path(tmp) / ".env"
            dotenv.write_text("DEBUG=1\n")
            with mock.patch("punzh.dotenv.DOTENV_PATH", dotenv):
                watch_dotenv(sender)
            self.assertEqual(sender.extra_files, {dotenv})

    def test_watch_skips_missing_dotenv(self):
        sender = mock.Mock()
        sender.extra_files = set()
        missing = Path("/tmp/punzh-dotenv-missing")
        with mock.patch("punzh.dotenv.DOTENV_PATH", missing):
            watch_dotenv(sender)
        self.assertEqual(sender.extra_files, set())
