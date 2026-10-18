from django.db import migrations, models


def set_logic_from_operator(apps, schema_editor):
    CollectRule = apps.get_model("mails", "CollectRule")
    for rule in CollectRule.objects.all():
        count = rule.conditions.count()
        if count <= 1:
            expr = "A"
        elif rule.operator == "or":
            expr = " OR ".join(chr(ord("A") + i) for i in range(count))
        else:
            expr = " AND ".join(chr(ord("A") + i) for i in range(count))
        rule.logic_expr = expr
        CollectRule.objects.filter(pk=rule.pk).update(logic_expr=expr)


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0011_collectrule_icon_and_logic"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectrule",
            name="logic_expr",
            field=models.CharField(
                default="A",
                help_text="Boolean expression over condition letters, e.g. (A OR B) AND C",
                max_length=255,
                verbose_name="Logic",
            ),
        ),
        migrations.RunPython(set_logic_from_operator, migrations.RunPython.noop),
        migrations.RemoveField(model_name="collectrule", name="operator"),
    ]
