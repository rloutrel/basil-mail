from django.db import migrations, models

LIGHT_TO_DARK = {
    "#2f6f4f": "#6fbf8f",
    "#1f6fb2": "#74b3ef",
    "#b2531f": "#f0a35e",
    "#a21fb2": "#d98ff0",
    "#b21f4f": "#f280a8",
    "#5a6470": "#a8b3bf",
    "#0b7285": "#66c9db",
    "#6b8e23": "#b3cf62",
    "#c2a018": "#e6c65a",
    "#7a1f1f": "#e07575",
}


def set_dark_colors(apps, schema_editor):
    MailSource = apps.get_model("mails", "MailSource")
    for source in MailSource.objects.all():
        dark = LIGHT_TO_DARK.get(
            (source.color or "").lower(), "#6fbf8f"
        )
        MailSource.objects.filter(pk=source.pk).update(color_dark=dark)


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0004_mailsource_symbol_bootstrap_icon"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailsource",
            name="color_dark",
            field=models.CharField(
                default="#6fbf8f",
                max_length=7,
                verbose_name="Color (dark)",
            ),
        ),
        migrations.RunPython(set_dark_colors, migrations.RunPython.noop),
    ]
