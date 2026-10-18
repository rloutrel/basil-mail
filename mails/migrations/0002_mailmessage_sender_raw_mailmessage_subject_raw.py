from django.db import migrations, models
from django.db.models import Q


def decode_header_value(raw):
    if not raw:
        return ""
    import email.header

    raw = raw.replace("\r\n ", " ").replace("\n ", " ")
    try:
        parts = email.header.decode_header(raw)
        decoded = []
        for text, charset in parts:
            if isinstance(text, bytes):
                decoded.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(text)
        return "".join(decoded)
    except Exception:
        return raw


def backfill_raw_headers(apps, schema_editor):
    MailMessage = apps.get_model("mails", "MailMessage")
    qs = MailMessage.objects.filter(
        Q(sender_raw="") | Q(subject_raw="")
    ).only("id", "sender", "subject", "sender_raw", "subject_raw")
    for mail in qs.iterator():
        changed = False
        if not mail.sender_raw:
            mail.sender_raw = mail.sender
        # Re-decode the stored (previously raw) value into the decoded field.
        if mail.sender and mail.sender != decode_header_value(mail.sender):
            mail.sender = decode_header_value(mail.sender)[:998]
            changed = True
        if not mail.subject_raw:
            mail.subject_raw = mail.subject
        if mail.subject and mail.subject != decode_header_value(mail.subject):
            mail.subject = decode_header_value(mail.subject)[:998]
            changed = True
        mail.save(
            update_fields=[
                "sender",
                "subject",
                "sender_raw",
                "subject_raw",
            ]
        )


def reverse_backfill(apps, schema_editor):
    MailMessage = apps.get_model("mails", "MailMessage")
    MailMessage.objects.update(sender_raw="", subject_raw="")


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailmessage",
            name="sender_raw",
            field=models.CharField(
                blank=True,
                default="",
                max_length=998,
                verbose_name="Sender (raw)",
            ),
        ),
        migrations.AddField(
            model_name="mailmessage",
            name="subject_raw",
            field=models.CharField(
                blank=True,
                max_length=998,
                default="",
                verbose_name="Subject (raw)",
            ),
        ),
        migrations.RunPython(backfill_raw_headers, reverse_backfill),
    ]
