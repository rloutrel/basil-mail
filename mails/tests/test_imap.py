import email as email_lib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import format_datetime
from datetime import datetime, timezone as dt_timezone
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from mails.imap import (
    decode_header_value,
    apply_rules,
    extract_body,
    extract_date,
    extract_link,
    fetch_source,
    run_fetch,
)
from mails.models import CollectRule, MailMessage, MailSource, RuleMatch


def make_raw(subject="Hello", sender="alice@example.com", body="Hi there",
             message_id="<1@example.com>", html=None, date=None):
    if html:
        msg = MIMEMultipart("alternative")
        msg.attach(MIMEText(body, "plain"))
        msg.attach(MIMEText(html, "html"))
    else:
        msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = "bob@example.com"
    msg["Message-ID"] = message_id
    if date:
        msg["Date"] = format_datetime(
            datetime.fromisoformat(date).replace(tzinfo=dt_timezone.utc)
        )
    else:
        msg["Date"] = format_datetime(
            datetime(2026, 1, 15, 12, 0, tzinfo=dt_timezone.utc)
        )
    return msg.as_bytes()


class FakeIMAP:
    """Minimal in-memory IMAP server: never mutates any state."""

    def __init__(self, messages):
        self.messages = messages
        self.readonly = None
        self.logged_out = False

    def login(self, username, password):
        return ("OK", [b"Logged in"])

    def select(self, folder, readonly=False):
        self.readonly = readonly
        self.selected = folder
        if folder not in ("INBOX", "Archive"):
            return ("NO", [b"Folder not found"])
        return ("OK", [str(len(self.messages)).encode()])

    def search(self, charset, criteria):
        return ("OK", [b" ".join(str(i).encode() for i in range(len(self.messages)))])

    def fetch(self, uid, spec):
        assert "BODY.PEEK" in spec, "must never set the \\Seen flag"
        uid = int(uid)
        return ("OK", [(b"%d" % uid, self.messages[uid])])

    def login(self, username, password):
        return ("OK", [b"Logged in"])

    def logout(self):
        self.logged_out = True


class HeaderDecodingTests(TestCase):
    def test_base64_utf8_sender(self):
        raw = "=?UTF-8?B?QWxla3NhbmRhciDEkG9yxJFldmnEhyB2aWEgWElORw==?= <mailrobot@mail.xing.com>"
        self.assertEqual(
            decode_header_value(raw),
            "Aleksandar Đorđević via XING <mailrobot@mail.xing.com>",
        )

    def test_quoted_printable_sender(self):
        raw = "=?utf-8?q?Caf=C3=A9=20r=C3=A9union?= <a@b.c>"
        self.assertEqual(decode_header_value(raw), "Café réunion <a@b.c>")

    def test_plain_sender_unchanged(self):
        self.assertEqual(
            decode_header_value("Plain <a@b.c>"), "Plain <a@b.c>"
        )

    def test_empty_header(self):
        self.assertEqual(decode_header_value(""), "")

    def test_fetch_stores_decoded_sender_and_subject(self):
        source = MailSource.objects.create(name="S", host="h", username="u")
        raw = make_raw(
            subject="=?UTF-8?B?QWpvYg==?=",
            sender="=?UTF-8?B?QWxla3NhbmRhciDEkG9yxJFldmnEhyB2aWEgWElORw==?= <mailrobot@mail.xing.com>",
        )
        from mails.imap import fetch_source
        from mails.tests.test_imap import FakeIMAP
        fetch_source(source, lambda s: FakeIMAP([raw]))
        mail = MailMessage.objects.get()
        self.assertEqual(mail.subject, "Ajob")
        self.assertEqual(
            mail.sender,
            "Aleksandar Đorđević via XING <mailrobot@mail.xing.com>",
        )

    def test_fetch_stores_raw_header_alongside_decoded(self):
        source = MailSource.objects.create(name="S", host="h", username="u")
        encoded_subject = "=?UTF-8?B?QWpvYg==?="
        raw = make_raw(subject=encoded_subject, sender="alice@example.com")
        from mails.imap import fetch_source
        fetch_source(source, lambda s: FakeIMAP([raw]))
        mail = MailMessage.objects.get()
        self.assertEqual(mail.subject, "Ajob")
        self.assertTrue(mail.subject_raw)
        self.assertIn(encoded_subject, mail.subject_raw)
        self.assertEqual(mail.sender, "alice@example.com")
        self.assertEqual(mail.sender_raw, "alice@example.com")


class BodyExtractionTests(TestCase):
    def test_plain_text_body(self):
        raw = make_raw(body="Hello\nWorld")
        msg = email_lib.message_from_bytes(raw)
        self.assertIn("Hello", extract_body(msg))
        self.assertIn("World", extract_body(msg))

    def test_html_fallback(self):
        raw = make_raw(body="", html="<p>Visit <b>us</b></p>")
        msg = email_lib.message_from_bytes(raw)
        body = extract_body(msg)
        self.assertIn("Visit us", body)
        self.assertNotIn("<b>", body)

    def test_link_extraction(self):
        self.assertEqual(
            extract_link("See https://example.com/page for details."),
            "https://example.com/page",
        )

    def test_link_extraction_trailing_punctuation(self):
        self.assertEqual(
            extract_link("Go to https://example.com/x."),
            "https://example.com/x",
        )

    def test_no_link(self):
        self.assertEqual(extract_link("no links here"), "")

    def test_date_extraction(self):
        raw = make_raw()
        msg = email_lib.message_from_bytes(raw)
        date = extract_date(msg)
        self.assertIsNotNone(date)
        self.assertEqual(date.year, 2026)

    def test_missing_date(self):
        msg = MIMEText("b", "plain")
        msg["Subject"] = "s"
        self.assertIsNone(extract_date(msg))


class FetchSourceTests(TestCase):
    def setUp(self):
        self.source = MailSource.objects.create(
            name="Test", host="imap.example.com", username="u", password="p"
        )

    def _factory(self, messages):
        def factory(source):
            return FakeIMAP(messages)
        return factory

    def test_fetch_stores_new_messages(self):
        raw = make_raw()
        count = fetch_source(self.source, self._factory([raw]))
        self.assertEqual(count, 1)
        mail = MailMessage.objects.get(source=self.source)
        self.assertEqual(mail.message_id, "<1@example.com>")
        self.assertEqual(mail.sender, "alice@example.com")
        self.assertEqual(mail.subject, "Hello")
        self.assertIn("Hi there", mail.body)
        self.assertEqual(mail.link, "")
        self.assertIsNotNone(mail.date)

    def test_deduplication_by_message_id(self):
        raw = make_raw()
        fetch_source(self.source, self._factory([raw]))
        count = fetch_source(self.source, self._factory([raw]))
        self.assertEqual(count, 0)
        self.assertEqual(MailMessage.objects.count(), 1)

    def test_deduplication_across_fetches_same_source(self):
        raw1 = make_raw(message_id="<1@example.com>")
        raw2 = make_raw(subject="Second", message_id="<2@example.com>")
        fetch_source(self.source, self._factory([raw1]))
        fetch_source(self.source, self._factory([raw1, raw2]))
        self.assertEqual(MailMessage.objects.count(), 2)

    def test_link_extracted_from_body(self):
        raw = make_raw(body="Apply at https://jobs.example.com/42 today")
        fetch_source(self.source, self._factory([raw]))
        mail = MailMessage.objects.get()
        self.assertEqual(mail.link, "https://jobs.example.com/42")

    def test_rules_applied_on_fetch(self):
        from mails.models import RuleCondition
        rule = CollectRule.objects.create(name="jobs", enabled=True)
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="regex", value="(?i)job"
        )
        raw = make_raw(subject="Job offer inside")
        fetch_source(self.source, self._factory([raw]))
        mail = MailMessage.objects.get()
        self.assertEqual(mail.rule_matches.count(), 1)
        self.assertEqual(mail.rule_matches.first().rule.name, "jobs")

    def test_select_uses_readonly(self):
        raw = make_raw()
        holder = {}

        def factory(source):
            holder["conn"] = FakeIMAP([raw])
            return holder["conn"]

        fetch_source(self.source, factory)
        self.assertTrue(holder["conn"].readonly)

    def test_select_error_raises(self):
        class BrokenSelect(FakeIMAP):
            def select(self, folder, readonly=False):
                return ("NO", [b"nope"])

        with self.assertRaises(ConnectionError):
            fetch_source(self.source, lambda s: BrokenSelect([]))

    def test_login_called_before_select(self):
        calls = []

        class TrackedIMAP(FakeIMAP):
            def login(self, username, password):
                calls.append("login")
                return super().login(username, password)

            def select(self, folder, readonly=False):
                calls.append("select")
                return super().select(folder, readonly=readonly)

        fetch_source(self.source, lambda s: TrackedIMAP([make_raw()]))
        self.assertEqual(calls[:2], ["login", "select"])

    def test_login_failure_raises_connection_error(self):
        class BadLogin(FakeIMAP):
            def login(self, username, password):
                return ("NO", [b"Authentication failed"])

        with self.assertRaises(ConnectionError):
            fetch_source(self.source, lambda s: BadLogin([make_raw()]))

    def test_logout_called(self):
        raw = make_raw()
        factory = self._factory([raw])
        conn_holder = {}

        def tracked(source):
            conn_holder["conn"] = factory(source)
            return conn_holder["conn"]

        fetch_source(self.source, tracked)
        self.assertTrue(conn_holder["conn"].logged_out)


class RunFetchTests(TestCase):
    def setUp(self):
        self.source = MailSource.objects.create(
            name="Test", host="h", username="u", fetch_frequency=15
        )

    def factory(self, messages):
        def factory(source):
            return FakeIMAP(messages)
        return factory

    def test_run_fetch_updates_last_fetch_at(self):
        raw = make_raw()
        results = run_fetch(connection_factory=self.factory([raw]))
        self.assertEqual(results["Test"]["new"], 1)
        self.source.refresh_from_db()
        self.assertIsNotNone(self.source.last_fetch_at)

    def test_run_fetch_skips_when_interval_not_elapsed(self):
        self.source.last_fetch_at = timezone.now()
        self.source.save()
        results = run_fetch(connection_factory=self.factory([make_raw()]))
        self.assertEqual(results, {})

    def test_run_fetch_skips_disabled_sources(self):
        self.source.enabled = False
        self.source.save()
        results = run_fetch(connection_factory=self.factory([make_raw()]))
        self.assertEqual(results, {})

    def test_run_fetch_continues_after_error(self):
        source2 = MailSource.objects.create(name="Second", host="h", username="u")

        def factory(source):
            if source.pk == source2.pk:
                raise OSError("connection refused")
            return FakeIMAP([make_raw(message_id="<ok@example.com>")])

        results = run_fetch(connection_factory=factory)
        self.assertIn("error", results["Second"])
        self.assertEqual(results["Test"]["new"], 1)

    def test_fetch_mails_command(self):
        from django.core.management import call_command
        raw = make_raw()
        with mock.patch("mails.imap._default_connection_factory",
                       side_effect=lambda s: FakeIMAP([raw])):
            call_command("fetch_mails", stdout=mock.MagicMock())
        self.assertEqual(MailMessage.objects.count(), 1)
