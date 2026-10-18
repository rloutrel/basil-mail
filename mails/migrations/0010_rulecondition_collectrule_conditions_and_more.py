from django.db import migrations, models
import django.db.models.deletion


def move_values_to_conditions(apps, schema_editor):
    CollectRule = apps.get_model("mails", "CollectRule")
    RuleCondition = apps.get_model("mails", "RuleCondition")
    for rule in CollectRule.objects.all():
        RuleCondition.objects.create(
            rule=rule,
            target_field=rule.target_field,
            match_type=rule.match_type,
            value=rule.value,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0009_alter_mailsource_host"),
    ]

    operations = [
        migrations.CreateModel(
            name="RuleCondition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("target_field", models.CharField(choices=[("sender", "Sender"), ("subject", "Subject"), ("body", "Body")], max_length=20, verbose_name="Target field")),
                ("match_type", models.CharField(choices=[("exact", "Exact match"), ("regex", "Regular expression")], default="exact", max_length=20, verbose_name="Match type")),
                ("value", models.CharField(max_length=255, verbose_name="Value")),
                ("rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conditions", to="mails.collectrule", verbose_name="Rule")),
            ],
            options={
                "verbose_name": "Rule condition",
                "verbose_name_plural": "Rule conditions",
                "ordering": ["pk"],
            },
        ),
        migrations.RunPython(move_values_to_conditions, migrations.RunPython.noop),
        migrations.RemoveField(model_name="collectrule", name="target_field"),
        migrations.RemoveField(model_name="collectrule", name="match_type"),
        migrations.RemoveField(model_name="collectrule", name="value"),
    ]
