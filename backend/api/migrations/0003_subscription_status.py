from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0002_telegramprofile"),
    ]

    operations = [
        migrations.AddField(
            model_name="subscription",
            name="last_check_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="last_success_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="last_item_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="subscription",
            name="last_error",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="subscription",
            name="consecutive_errors",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
