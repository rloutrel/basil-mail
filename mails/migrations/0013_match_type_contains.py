from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("mails", "0012_collectrule_logic_expr"),
    ]

    operations = [
        migrations.RunSQL(
            "UPDATE mails_rulecondition SET match_type = 'contains' "
            "WHERE match_type = 'exact';",
            reverse_sql="UPDATE mails_rulecondition SET match_type = 'exact' "
            "WHERE match_type = 'contains';",
        ),
        migrations.AlterField(
            model_name="rulecondition",
            name="match_type",
            field=models.CharField(
                choices=[("contains", "Contains"), ("regex", "Regex")],
                default="contains",
                max_length=20,
                verbose_name="Match type",
            ),
        ),
    ]
