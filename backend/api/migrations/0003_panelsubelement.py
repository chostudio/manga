from django.db import migrations, models
import django.db.models.deletion
import pgvector.django


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0002_storedpanel_embedding"),
    ]

    operations = [
        migrations.CreateModel(
            name="PanelSubElement",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "panel",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sub_elements",
                        to="api.storedpanel",
                    ),
                ),
                (
                    "label",
                    models.CharField(
                        choices=[
                            ("face", "face"),
                            ("hair", "hair"),
                            ("hand", "hand"),
                            ("clothing", "clothing"),
                        ],
                        db_index=True,
                        max_length=64,
                    ),
                ),
                ("bbox", models.JSONField(blank=True, null=True)),
                (
                    "embedding",
                    pgvector.django.VectorField(
                        blank=True, dimensions=512, null=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["panel", "label"],
            },
        ),
    ]
