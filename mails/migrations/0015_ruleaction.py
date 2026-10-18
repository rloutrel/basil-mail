from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0014_alter_collectrule_logic_expr"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuleAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("action_type", models.CharField(choices=[("mark_read", "Mark as read"), ("http_callback", "Send to REST callback")], default="mark_read", max_length=20, verbose_name="Action")),
                ("callback_url", models.URLField(blank=True, default="", max_length=2048, verbose_name="Callback URL")),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="actions", to="mails.collectrule", verbose_name="Rule")),
            ],
            options={
                "verbose_name": "Rule action",
                "verbose_name_plural": "Rule actions",
                "ordering": ["pk"],
            },
        ),
    ]
