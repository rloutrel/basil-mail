from django.contrib import admin

from .models import (
    CollectRule,
    MailMessage,
    MailSource,
    RuleAction,
    RuleCondition,
    RuleMatch,
)


class RuleMatchInline(admin.TabularInline):
    model = RuleMatch
    extra = 0


@admin.register(MailSource)
class MailSourceAdmin(admin.ModelAdmin):
    list_display = ("name", "host", "port", "enabled", "last_fetch_at")
    list_filter = ("enabled",)


@admin.register(MailMessage)
class MailMessageAdmin(admin.ModelAdmin):
    list_display = ("subject", "sender", "source", "date", "read_by_me")
    list_filter = ("source", "read_by_me")
    search_fields = ("sender", "subject", "body")
    fields = (
        "source",
        "message_id",
        "sender",
        "sender_raw",
        "subject",
        "subject_raw",
        "date",
        "body",
        "link",
        "read_by_me",
    )
    inlines = [RuleMatchInline]


class RuleConditionInline(admin.TabularInline):
    model = RuleCondition
    extra = 0


class RuleActionInline(admin.TabularInline):
    model = RuleAction
    extra = 0


@admin.register(CollectRule)
class CollectRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "enabled")
    list_filter = ("enabled",)
    inlines = [RuleConditionInline, RuleActionInline]


@admin.register(RuleMatch)
class RuleMatchAdmin(admin.ModelAdmin):
    list_display = ("rule", "mail", "matched_at")
    list_filter = ("rule",)
