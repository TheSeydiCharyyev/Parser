from django.db import migrations, models

import api.validators


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0003_subscription_status"),
    ]

    operations = [
        migrations.AlterField(
            model_name="subscription",
            name="url",
            field=models.CharField(
                max_length=2048,
                verbose_name="Ссылка",
                validators=[api.validators.validate_http_url_allow_internal],
            ),
        ),
    ]
