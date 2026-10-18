from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0015_ruleaction"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuleActionLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("executed_at", models.DateTimeField(auto_now_add=True, verbose_name="Executed at")),
                ("action", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="logs", to="mails.ruleaction", verbose_name="Action")),
                ("mail", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="action_logs", to="mails.mailmessage", verbose_name="Mail")),
            ],
            options={
                "verbose_name": "Rule action log",
                "verbose_name_plural": "Rule action logs",
            },
        ),
        migrations.AddConstraint(
            model_name="ruleactionlog",
            constraint=models.UniqueConstraint(fields=("action", "mail"), name="unique_action_mail"),
        ),
    ]
