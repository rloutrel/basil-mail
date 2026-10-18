from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0016_ruleactionlog"),
    ]

    operations = [
        migrations.AddField(
            model_name="collectrule",
            name="apply_to_existing",
            field=models.BooleanField(
                default=False,
                help_text="On save, run the rule's actions on the currently matching mails; otherwise only newly collected mails trigger them.",
                verbose_name="Apply to existing mails",
            ),
        ),
    ]
