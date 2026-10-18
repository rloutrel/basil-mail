import re

from django import forms
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils.translation import gettext_lazy as _
from django.views import generic

from .imap import reapply_rule, run_fetch
from .models import (
    CollectRule,
    MailMessage,
    MailSource,
    RuleAction,
    RuleCondition,
)

PAGE_SIZE = 25


class MaskedTextInput(forms.TextInput):
    """Text input that never renders its current value, so the stored
    IMAP password is never sent to the browser and never offered to
    be saved as a credential (it is not a password-type input)."""

    def get_context(self, name, value, attrs):
        return super().get_context(name, "", attrs)


class MailSourceForm(forms.ModelForm):
    class Meta:
        model = MailSource
        fields = [
            "name",
            "host",
            "port",
            "use_ssl",
            "username",
            "password",
            "folder",
            "symbol",
            "color",
            "color_dark",
            "fetch_frequency",
        ]
        widgets = {
            "password": MaskedTextInput(
                attrs={
                    "class": "masked-text",
                    "autocomplete": "off",
                    "spellcheck": "false",
                    "autocapitalize": "none",
                }
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["symbol"].required = False
        self.fields["color"].required = False
        self.fields["color_dark"].required = False
        self.fields["password"].required = False

    def clean_symbol(self):
        return self.cleaned_data.get("symbol") or "envelope"

    def clean_password(self):
        password = self.cleaned_data.get("password") or ""
        if not password:
            if self.instance and self.instance.pk:
                return self.instance.password
            raise forms.ValidationError(_("This field is required."))
        return password

    def clean_color(self):
        color = (self.cleaned_data.get("color") or "").strip() or "#2f6f4f"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise forms.ValidationError(_("Invalid color."))
        return color

    def clean_color_dark(self):
        color = (self.cleaned_data.get("color_dark") or "").strip() or "#6fbf8f"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise forms.ValidationError(_("Invalid color."))
        return color


class CollectRuleForm(forms.ModelForm):
    class Meta:
        model = CollectRule
        fields = [
            "name",
            "logic_expr",
            "apply_to_existing",
            "symbol",
            "color",
            "color_dark",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["symbol"].required = False
        self.fields["color"].required = False
        self.fields["color_dark"].required = False

    def clean_logic_expr(self):
        from .logic import compile_expression, LogicError

        expression = (self.cleaned_data.get("logic_expr") or "").strip()
        if not expression:
            expression = "A"
        try:
            compile_expression(expression)
        except LogicError as exc:
            raise forms.ValidationError(_("Invalid logic: %s") % exc)
        return expression

    def clean_symbol(self):
        return self.cleaned_data.get("symbol") or "star"

    def clean_color(self):
        color = (self.cleaned_data.get("color") or "").strip() or "#c2a018"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise forms.ValidationError(_("Invalid color."))
        return color

    def clean_color_dark(self):
        color = (self.cleaned_data.get("color_dark") or "").strip() or "#e6c65a"
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise forms.ValidationError(_("Invalid color."))
        return color


class RuleConditionForm(forms.ModelForm):
    class Meta:
        model = RuleCondition
        fields = ["target_field", "match_type", "value", "negate"]

    def clean_value(self):
        match_type = self.cleaned_data.get("match_type")
        value = self.cleaned_data.get("value") or ""
        if match_type == "regex":
            try:
                re.compile(value)
            except re.error:
                raise forms.ValidationError(_("Invalid regular expression."))
        return value


class RuleActionForm(forms.ModelForm):
    class Meta:
        model = RuleAction
        fields = ["action_type", "callback_url"]
        widgets = {
            "action_type": forms.Select(
                attrs={"required": "required"}
            )
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # no initial default: force the user's choice to count as a change
        if not self.instance.pk:
            self.initial["action_type"] = ""

    def save(self, *args, **kwargs):
        """Clear the execution log when the action changes, so the
        (potentially new) callback re-fires for existing mails on the
        next 'Apply to existing mails' save."""
        action = super().save(*args, **kwargs)
        if action.pk:
            changed_fields = []
            for field in ("action_type", "callback_url"):
                if field in self.changed_data:
                    changed_fields.append(field)
            if changed_fields:
                action.logs.all().delete()
        return action

    def clean(self):
        cleaned = super().clean()
        action_type = cleaned.get("action_type")
        callback_url = (cleaned.get("callback_url") or "").strip()
        if action_type == "http_callback" and not callback_url:
            raise forms.ValidationError(
                _("A callback URL is required for this action.")
            )
        return cleaned


RuleActionFormSet = forms.inlineformset_factory(
    CollectRule,
    RuleAction,
    form=RuleActionForm,
    extra=0,
    can_delete=True,
)


RuleConditionFormSet = forms.inlineformset_factory(
    CollectRule,
    RuleCondition,
    form=RuleConditionForm,
    extra=0,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


def filtered_mails(request):
    """Apply AND-logic filters from the query string; return (qs, filters)."""
    filters = {
        "rule": request.GET.get("rule", ""),
        "source": request.GET.get("source", ""),
        "sender": request.GET.get("sender", "").strip(),
        "subject": request.GET.get("subject", "").strip(),
    }
    qs = MailMessage.objects.select_related("source").prefetch_related(
        "rule_matches__rule"
    )
    rule = filters["rule"]
    if rule:
        if rule == "unsorted":
            qs = qs.filter(rule_matches__isnull=True)
        else:
            qs = qs.filter(rule_matches__rule__pk=_pk_or_none(rule))
    if filters["source"]:
        qs = qs.filter(source__pk=_pk_or_none(filters["source"]))
    if filters["sender"]:
        qs = qs.filter(sender__icontains=filters["sender"])
    if filters["subject"]:
        qs = qs.filter(subject__icontains=filters["subject"])
    return qs.distinct(), filters


def _pk_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sender_suggestions(limit=200):
    return list(
        MailMessage.objects.values_list("sender", flat=True)
        .annotate(freq=Count("id"))
        .order_by("-freq")[:limit]
    )


def _page_context(request, extra=None):
    qs, filters = filtered_mails(request)
    paginator = Paginator(qs, PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page", 1))
    context = {
        "page": page,
        "mails": page.object_list,
        "filters": filters,
        "total_count": paginator.count,
    }
    if extra:
        context.update(extra)
    return context


def mail_list(request):
    context = _page_context(
        request,
        {
            "sources": MailSource.objects.order_by("name"),
            "rules": CollectRule.objects.order_by("name"),
        },
    )
    return render(request, "mails/mail_list.html", context)


def mail_table(request):
    """HTMX partial: only the table, used when filters change."""
    return render(request, "mails/partials/mail_table.html", _page_context(request))


def mail_detail(request, pk):
    mail = get_object_or_404(
        MailMessage.objects.select_related("source").prefetch_related(
            "rule_matches__rule"
        ),
        pk=pk,
    )
    return render(request, "mails/partials/mail_detail.html", {"mail": mail})


def fetch_now(request):
    """Trigger an asynchronous fetch (fire-and-forget)."""
    import threading

    threading.Thread(target=run_fetch, daemon=True).start()
    return HttpResponse(status=202)


def config_page(request):
    request.META["CSRF_COOKIE_NEEDS_UPDATE"] = True
    sources = MailSource.objects.order_by("name")
    rules = CollectRule.objects.annotate(mail_count=Count("matches")).order_by(
        "name"
    )
    context = {
        "sources": sources,
        "rules": rules,
        "source_forms": {
            source.pk: MailSourceForm(
                instance=source, prefix="source-%d" % source.pk
            )
            for source in sources
        },
        "rule_forms": {
            rule.pk: CollectRuleForm(instance=rule, prefix="rule-%d" % rule.pk)
            for rule in rules
        },
        "rule_condition_forms": {
            rule.pk: RuleConditionFormSet(
                instance=rule, prefix="rule-%d-conditions" % rule.pk
            )
            for rule in rules
        },
        "rule_action_forms": {
            rule.pk: RuleActionFormSet(
                instance=rule, prefix="rule-%d-actions" % rule.pk
            )
            for rule in rules
        },
        "source_symbols": MailSource.SYMBOLS,
        "source_colors": MailSource.COLOR_PAIRS,
        "sender_suggestions": _sender_suggestions(),
    }
    return render(request, "mails/config/config.html", context)


def _config_body(
    request,
    error_source_forms=None,
    error_rule_forms=None,
    error_rule_condition_forms=None,
):
    sources = MailSource.objects.order_by("name")
    rules = CollectRule.objects.annotate(mail_count=Count("matches")).order_by(
        "name"
    )
    source_forms = {
        source.pk: MailSourceForm(instance=source, prefix="source-%d" % source.pk)
        for source in sources
    }
    rule_forms = {
        rule.pk: CollectRuleForm(instance=rule, prefix="rule-%d" % rule.pk)
        for rule in rules
    }
    rule_condition_forms = {
        rule.pk: RuleConditionFormSet(
            instance=rule, prefix="rule-%d-conditions" % rule.pk
        )
        for rule in rules
    }
    rule_action_forms = {
        rule.pk: RuleActionFormSet(
            instance=rule, prefix="rule-%d-actions" % rule.pk
        )
        for rule in rules
    }
    if error_source_forms:
        source_forms.update(error_source_forms)
    if error_rule_forms:
        rule_forms.update(error_rule_forms)
    if error_rule_condition_forms:
        rule_condition_forms.update(error_rule_condition_forms)
    context = {
        "sources": sources,
        "rules": rules,
        "source_forms": source_forms,
        "rule_forms": rule_forms,
        "rule_condition_forms": rule_condition_forms,
        "rule_action_forms": rule_action_forms,
        "source_symbols": MailSource.SYMBOLS,
        "source_colors": MailSource.COLOR_PAIRS,
        "sender_suggestions": _sender_suggestions(),
    }
    return render(request, "mails/partials/config_body.html", context)


def source_create(request):
    if request.method == "POST":
        form = MailSourceForm(request.POST, prefix="source-new")
        if form.is_valid():
            form.save()
            return _config_body(request)
    else:
        form = MailSourceForm(prefix="source-new")
    return render(
        request,
        "mails/partials/source_form.html",
        {
            "form": form,
            "source_symbols": MailSource.SYMBOLS,
            "source_colors": MailSource.COLOR_PAIRS,
        },
    )


def source_update(request, pk):
    source = get_object_or_404(MailSource, pk=pk)
    if request.method == "POST":
        form = MailSourceForm(
            request.POST, instance=source, prefix="source-%d" % pk
        )
        if form.is_valid():
            form.save()
            return _source_card(request, source)
        return _source_card(request, source, error_forms=form)
    return _config_body(request)


def _source_card(request, source, error_forms=None):
    sources = [source]
    context = {
        "sources": sources,
        "rules": [],
        "source_forms": {
            source.pk: error_forms or MailSourceForm(
                instance=source, prefix="source-%d" % source.pk
            )
        },
        "rule_forms": {},
        "source_symbols": MailSource.SYMBOLS,
        "source_colors": MailSource.COLOR_PAIRS,
    }
    return render(request, "mails/partials/source_card.html", context)


def source_rename(request, pk):
    source = get_object_or_404(MailSource, pk=pk)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if name and name != source.name:
            source.name = name
            source.save(update_fields=["name"])
        return _source_card(request, source)
    return _source_card(request, source)


def source_toggle(request, pk):
    source = get_object_or_404(MailSource, pk=pk)
    if request.method == "POST":
        source.enabled = not source.enabled
        source.save(update_fields=["enabled"])
        return _source_card(request, source)
    return _source_card(request, source)


def source_delete(request, pk):
    source = get_object_or_404(MailSource, pk=pk)
    if request.method == "POST":
        source.delete()
        return _config_body(request)
    return _config_body(request)


def source_test(request, pk):
    """Test the IMAP connection of a source (inline HTMX response)."""
    import imaplib

    source = get_object_or_404(MailSource, pk=pk)
    try:
        if source.use_ssl:
            conn = imaplib.IMAP4_SSL(source.host, source.port)
        else:
            conn = imaplib.IMAP4(source.host, source.port)
        try:
            conn.login(source.username, source.password)
            status, _data = conn.select(source.folder, readonly=True)
            if status != "OK":
                message = _("Connection succeeded but mailbox is not readable.")
                status_class = "error"
            else:
                message = _("Connection succeeded, mailbox is readable.")
                status_class = "ok"
        finally:
            try:
                conn.logout()
            except Exception:
                pass
    except Exception as exc:
        message = _("Connection failed: %(error)s") % {"error": exc}
        status_class = "error"
    return render(
        request,
        "mails/config/partials/test_result.html",
        {"message": message, "status_class": status_class},
    )


def rule_create(request):
    rule = CollectRule()
    if request.method == "POST":
        form = CollectRuleForm(request.POST, instance=rule, prefix="rule-new")
        formset = RuleConditionFormSet(
            request.POST, instance=rule, prefix="rule-new-conditions"
        )
        action_formset = RuleActionFormSet(
            request.POST, instance=rule, prefix="rule-new-actions"
        )
        if form.is_valid() and formset.is_valid() and action_formset.is_valid():
            rule = form.save()
            formset.instance = rule
            formset.save()
            action_formset.instance = rule
            action_formset.save()
            reapply_rule(rule)
            return _config_body(request)
    else:
        form = CollectRuleForm(instance=rule, prefix="rule-new")
        formset = RuleConditionFormSet(instance=rule, prefix="rule-new-conditions")
        action_formset = RuleActionFormSet(
            instance=rule, prefix="rule-new-actions"
        )
    return render(
        request,
        "mails/partials/rule_form.html",
        {
            "form": form,
            "condition_forms": formset,
            "action_forms": action_formset,
            "sender_suggestions": _sender_suggestions(),
            "source_symbols": MailSource.SYMBOLS,
            "source_colors": MailSource.COLOR_PAIRS,
        },
    )


def rule_update(request, pk):
    rule = get_object_or_404(CollectRule, pk=pk)
    if request.method == "POST":
        form = CollectRuleForm(request.POST, instance=rule, prefix="rule-%d" % pk)
        formset = RuleConditionFormSet(
            request.POST, instance=rule, prefix="rule-%d-conditions" % pk
        )
        action_formset = RuleActionFormSet(
            request.POST, instance=rule, prefix="rule-%d-actions" % pk
        )
        if (
            form.is_valid()
            and formset.is_valid()
            and action_formset.is_valid()
        ):
            import logging

            logger = logging.getLogger(__name__)
            rule = form.save()
            formset.instance = rule
            formset.save()
            action_formset.instance = rule
            action_formset.save()
            logger.info(
                "rule_update saved: rule=%r pk=%s enabled=%s "
                "apply_to_existing=%s conditions=%s actions=%s",
                rule.name, rule.pk, rule.enabled, rule.apply_to_existing,
                rule.conditions.count(), rule.actions.count(),
            )
            for action in rule.actions.all():
                logger.info(
                    "  action: type=%s pk=%s url=%r logs=%s",
                    action.action_type, action.pk, action.callback_url,
                    action.logs.count(),
                )
            if rule.enabled:
                reapply_rule(rule)
            return _rule_card(request, rule)
        return _rule_card(
            request,
            rule,
            error_forms=form,
            error_condition_forms=formset,
            error_action_forms=action_formset,
        )
    return _config_body(request)


def rule_rename(request, pk):
    rule = get_object_or_404(CollectRule, pk=pk)
    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        if name and name != rule.name:
            rule.name = name
            rule.save(update_fields=["name"])
        return _rule_card(request, rule)
    return _rule_card(request, rule)


def _rule_card(
    request,
    rule,
    error_forms=None,
    error_condition_forms=None,
    error_action_forms=None,
):
    rules = CollectRule.objects.filter(pk=rule.pk).annotate(
        mail_count=Count("matches")
    )
    rule_forms = {
        rule.pk: error_forms or CollectRuleForm(
            instance=rule, prefix="rule-%d" % rule.pk
        )
    }
    rule_condition_forms = {
        rule.pk: error_condition_forms or RuleConditionFormSet(
            instance=rule, prefix="rule-%d-conditions" % rule.pk
        )
    }
    rule_action_forms = {
        rule.pk: error_action_forms or RuleActionFormSet(
            instance=rule, prefix="rule-%d-actions" % rule.pk
        )
    }
    context = {
        "sources": [],
        "rules": rules,
        "source_forms": {},
        "rule_forms": rule_forms,
        "rule_condition_forms": rule_condition_forms,
        "rule_action_forms": rule_action_forms,
        "source_symbols": MailSource.SYMBOLS,
        "source_colors": MailSource.COLOR_PAIRS,
    }
    return render(request, "mails/partials/rule_card.html", context)


def rule_preview_count(request, pk):
    """Number of stored mails matching the rule with the posted logic
    (conditions taken from the posted formset when provided)."""
    import json

    from django.http import JsonResponse

    from .logic import compile_expression, evaluate, LogicError

    rule = get_object_or_404(CollectRule, pk=pk)
    expression = (request.POST.get("logic") or "").strip()
    if not expression:
        return JsonResponse({"valid": False, "count": 0})
    try:
        ast = compile_expression(expression)
    except LogicError as exc:
        return JsonResponse({"valid": False, "count": 0, "error": str(exc)})

    conditions = rule.conditions.all()
    count = 0
    for mail in MailMessage.objects.all():
        values = {}
        for index, condition in enumerate(conditions):
            letter = chr(ord("A") + index)
            values[letter] = condition.matches_mail(mail)
        if evaluate(ast, values):
            count += 1
    return JsonResponse({"valid": True, "count": count})


def rule_toggle(request, pk):
    rule = get_object_or_404(CollectRule, pk=pk)
    if request.method == "POST":
        rule.enabled = not rule.enabled
        rule.save(update_fields=["enabled"])
        if rule.enabled:
            reapply_rule(rule)
        return _rule_card(request, rule)
    return _rule_card(request, rule)


def rule_delete(request, pk):
    rule = get_object_or_404(CollectRule, pk=pk)
    if request.method == "POST":
        rule.delete()
        return _config_body(request)
    return _config_body(request)


