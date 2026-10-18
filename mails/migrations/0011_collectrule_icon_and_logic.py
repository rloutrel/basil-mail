from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0010_rulecondition_collectrule_conditions_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectrule",
            name="operator",
            field=models.CharField(
                choices=[("and", "All conditions (AND)"), ("or", "Any condition (OR)")],
                default="and",
                max_length=5,
                verbose_name="Combination",
            ),
        ),
        migrations.AddField(
            model_name="collectrule",
            name="symbol",
            field=models.CharField(default="star", max_length=40, verbose_name="Symbol"),
        ),
        migrations.AddField(
            model_name="collectrule",
            name="color",
            field=models.CharField(default="#c2a018", max_length=7, verbose_name="Color (light)"),
        ),
        migrations.AddField(
            model_name="collectrule",
            name="color_dark",
            field=models.CharField(default="#e6c65a", max_length=7, verbose_name="Color (dark)"),
        ),
        migrations.AddField(
            model_name="rulecondition",
            name="negate",
            field=models.BooleanField(default=False, verbose_name="Negate (NOT)"),
        ),
    ]
