from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('relationships', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='relationmap',
            name='relation_data',
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
