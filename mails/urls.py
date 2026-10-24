from django.urls import path

from . import views

app_name = "mails"

urlpatterns = [
    path("", views.mail_list, name="mail_list"),
    path("mails/table/", views.mail_table, name="mail_table"),
    path("mails/<int:pk>/", views.mail_detail, name="mail_detail"),
    path("fetch/", views.fetch_now, name="fetch_now"),
    path("config/", views.config_page, name="config"),
    path("config/sources/new/", views.source_create, name="source_create"),
    path("config/sources/new/test/", views.source_test_new, name="source_test_new"),
    path("config/sources/<int:pk>/edit/", views.source_update, name="source_update"),
    path("config/sources/<int:pk>/delete/", views.source_delete, name="source_delete"),
    path("config/sources/<int:pk>/toggle/", views.source_toggle, name="source_toggle"),
    path("config/sources/<int:pk>/rename/", views.source_rename, name="source_rename"),
    path("config/sources/<int:pk>/test/", views.source_test, name="source_test"),
    path("config/rules/new/", views.rule_create, name="rule_create"),
    path("config/rules/<int:pk>/edit/", views.rule_update, name="rule_update"),
    path("config/rules/<int:pk>/delete/", views.rule_delete, name="rule_delete"),
    path("config/rules/<int:pk>/toggle/", views.rule_toggle, name="rule_toggle"),
    path("config/rules/<int:pk>/count/", views.rule_preview_count, name="rule_count"),
    path("config/rules/<int:pk>/rename/", views.rule_rename, name="rule_rename"),
]
