from django.apps import apps as global_apps
from django.test import TestCase

from mails.models import MailMessage, MailSource

ENCODED_SENDER = (
    "=?UTF-8?B?QWxla3NhbmRhciDEkG9yxJFldmnEhyB2aWEgWElORw==?= "
    "<mailrobot@mail.xing.com>"
)
ENCODED_SUBJECT = "=?UTF-8?B?QWpvYg==?="


class RawHeaderBackfillTests(TestCase):
    """The 0002 data migration decodes previously stored raw headers
    while preserving the original value in the *_raw fields."""

    def test_backfill_function(self):
        # Import the migration module and run its backfill against the
        # current (test) database.
        import importlib

        migration = importlib.import_module(
            "mails.migrations."
            "0002_mailmessage_sender_raw_mailmessage_subject_raw"
        )

        source = MailSource.objects.create(name="S", host="h", username="u")
        MailMessage.objects.create(
            source=source,
            message_id="<1@x>",
            sender=ENCODED_SENDER,
            subject=ENCODED_SUBJECT,
        )
        MailMessage.objects.create(
            source=source,
            message_id="<2@x>",
            sender="alice@example.com",
            subject="Plain subject",
        )

        migration.backfill_raw_headers(apps=global_apps, schema_editor=None)

        decoded = MailMessage.objects.get(message_id="<1@x>")
        self.assertEqual(
            decoded.sender,
            "Aleksandar Đorđević via XING <mailrobot@mail.xing.com>",
        )
        self.assertEqual(decoded.sender_raw, ENCODED_SENDER)
        self.assertEqual(decoded.subject, "Ajob")
        self.assertEqual(decoded.subject_raw, ENCODED_SUBJECT)

        plain = MailMessage.objects.get(message_id="<2@x>")
        self.assertEqual(plain.sender, "alice@example.com")
        self.assertEqual(plain.sender_raw, "alice@example.com")
        self.assertEqual(plain.subject, "Plain subject")
        self.assertEqual(plain.subject_raw, "Plain subject")

    def test_backfill_is_idempotent(self):
        import importlib

        migration = importlib.import_module(
            "mails.migrations."
            "0002_mailmessage_sender_raw_mailmessage_subject_raw"
        )

        source = MailSource.objects.create(name="S", host="h", username="u")
        MailMessage.objects.create(
            source=source,
            message_id="<1@x>",
            sender=ENCODED_SENDER,
            subject=ENCODED_SUBJECT,
        )

        migration.backfill_raw_headers(apps=global_apps, schema_editor=None)
        first = MailMessage.objects.get(message_id="<1@x>")
        migration.backfill_raw_headers(apps=global_apps, schema_editor=None)
        second = MailMessage.objects.get(message_id="<1@x>")

        self.assertEqual(first.sender, second.sender)
        self.assertEqual(first.sender_raw, second.sender_raw)
        self.assertEqual(first.subject, second.subject)
        self.assertEqual(first.subject_raw, second.subject_raw)
