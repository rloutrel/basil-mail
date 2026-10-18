from django.db import migrations, models

EMOJI_TO_ICON = {
    "✉": "envelope",
    "📧": "envelope-open",
    "📨": "envelope",
    "📩": "envelope",
    "📬": "inbox",
    "📭": "inbox",
    "📮": "envelope-paper",
    "🏠": "house",
    "💼": "briefcase",
    "👤": "person",
    "⭐": "star",
    "🔔": "bell",
    "🛒": "cart",
    "🎓": "journal",
    "❤": "heart",
    "🎉": "gift",
}


def convert_symbols_to_icons(apps, schema_editor):
    MailSource = apps.get_model("mails", "MailSource")
    for source in MailSource.objects.all():
        source.symbol = EMOJI_TO_ICON.get(source.symbol, "envelope")
        MailSource.objects.filter(pk=source.pk).update(symbol=source.symbol)


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0003_mailsource_color_mailsource_symbol"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mailsource",
            name="symbol",
            field=models.CharField(
                default="envelope", max_length=40, verbose_name="Symbol"
            ),
        ),
        migrations.RunPython(convert_symbols_to_icons, migrations.RunPython.noop),
    ]
