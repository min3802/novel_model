from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('characters', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='character',
            name='relation',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='character',
            name='source',
            field=models.CharField(
                choices=[('MANUAL', '수동 입력'), ('AI', 'AI 추출')],
                default='MANUAL',
                max_length=20,
            ),
        ),
    ]
