# Generated by Django 4.2.13 on 2024-05-24 21:30

from django.db import migrations, models
import django.db.models.deletion

def insert_default_acl(apps, schema_editor):
    Acl = apps.get_model('whctools', 'Acl')
    # Create a default Acl instance
    Acl.objects.create(name='WHC', description="Base WHC ACL listing")

class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('eveonline', '0017_alliance_and_corp_names_are_not_unique'),
    ]

    operations = [
        migrations.CreateModel(
            name='General',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ],
            options={
                'permissions': (('basic_access', 'Can access this app'), ('whc_officer', 'Can access officer side')),
                'managed': False,
                'default_permissions': (),
            },
        ),
        migrations.CreateModel(
            name='Acl',
            fields=[
                ('name', models.CharField(blank=True, max_length=255, primary_key=True, serialize=False)),
                ('description', models.TextField(blank=True, null=True)),
                ('characters', models.ManyToManyField(to='eveonline.evecharacter')),
            ],
        ),
        migrations.CreateModel(
            name='Applications',
            fields=[
                ('eve_character', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, serialize=False, to='eveonline.evecharacter')),
                ('member_state', models.IntegerField(choices=[(0, 'Not A Member'), (1, 'Applied'), (2, 'Rejected'), (3, 'Accepted')], default=0)),
                ('reject_reason', models.IntegerField(choices=[(0, 'Not Rejected'), (1, 'Insufficient Skills'), (2, 'Withdrawn Application'), (3, 'Removed From Community'), (99, 'Undisclosed')], default=0)),
                ('reject_timeout', models.DateTimeField(auto_now_add=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name_plural': 'Applications',
                'ordering': ['eve_character__character_name'],
            },
        ),
        migrations.CreateModel(
            name='ACLHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date_of_change', models.DateTimeField()),
                ('old_state', models.IntegerField(choices=[(0, 'Not A Member'), (1, 'Applied'), (2, 'Rejected'), (3, 'Accepted')], default=0)),
                ('new_state', models.IntegerField(choices=[(0, 'Not A Member'), (1, 'Applied'), (2, 'Rejected'), (3, 'Accepted')], default=0)),
                ('changed_by', models.CharField(blank=True, max_length=225)),
                ('acl', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='changes', to='whctools.acl')),
                ('character', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='eveonline.evecharacter')),
            ],
        ),
        migrations.RunPython(insert_default_acl),
    ]
