import re

from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _


def validate_regex(value):
    try:
        re.compile(value)
    except re.error:
        raise models.base.ValidationError(_("Invalid regular expression."))


TARGET_FIELD_CHOICES = [
    ("sender", _("Sender")),
    ("subject", _("Subject")),
    ("body", _("Body")),
]

MATCH_TYPE_CHOICES = [
    ("contains", _("Contains")),
    ("regex", _("Regex")),
]


class MailSource(models.Model):
    SYMBOLS = [
        "envelope", "envelope-open", "envelope-heart", "envelope-paper",
        "briefcase", "house", "house-heart", "person", "people",
        "star", "star-fill", "heart", "heart-fill", "bell", "bell-fill",
        "cart", "bag", "box", "inbox", "bookmark", "flag", "lightning",
        "gear", "cloud", "database", "journal", "camera", "globe",
        "chat", "send", "phone", "gift", "lightbulb", "newspaper",
    ]
    # (light-mode, dark-mode) color pairs used by the picker.
    COLOR_PAIRS = [
        ("#2f6f4f", "#6fbf8f"),
        ("#1f6fb2", "#74b3ef"),
        ("#b2531f", "#f0a35e"),
        ("#a21fb2", "#d98ff0"),
        ("#b21f4f", "#f280a8"),
        ("#5a6470", "#a8b3bf"),
        ("#0b7285", "#66c9db"),
        ("#6b8e23", "#b3cF62"),
        ("#c2a018", "#e6c65a"),
        ("#7a1f1f", "#e07575"),
    ]

    name = models.CharField(_("Name"), max_length=120, unique=True)
    host = models.CharField(_("Host"), max_length=255)
    port = models.PositiveIntegerField(_("Port"), default=993)
    use_ssl = models.BooleanField(_("SSL/TLS"), default=True)
    username = models.CharField(_("Username"), max_length=255)
    password = models.CharField(_("Password"), max_length=255)
    folder = models.CharField(_("Mailbox folder"), max_length=255, default="INBOX")
    symbol = models.CharField(_("Symbol"), max_length=40, default="envelope")
    color = models.CharField(_("Color (light)"), max_length=7, default="#2f6f4f")
    color_dark = models.CharField(
        _("Color (dark)"), max_length=7, default="#6fbf8f"
    )
    fetch_frequency = models.PositiveIntegerField(
        _("Frequency (m)"), default=15
    )
    enabled = models.BooleanField(_("Enabled"), default=True)
    last_fetch_at = models.DateTimeField(_("Last fetch"), null=True, blank=True)

    class Meta:
        verbose_name = _("Mail source")
        verbose_name_plural = _("Mail sources")
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def interval_elapsed(self):
        from django.utils import timezone

        if not self.enabled:
            return False
        if self.last_fetch_at is None:
            return True
        return timezone.now() >= self.last_fetch_at + timezone.timedelta(
            minutes=self.fetch_frequency
        )


class MailMessage(models.Model):
    source = models.ForeignKey(
        MailSource,
        on_delete=models.CASCADE,
        related_name="messages",
        verbose_name=_("Source"),
    )
    message_id = models.CharField(_("Message-ID"), max_length=998)
    sender = models.CharField(_("Sender"), max_length=998, blank=True, default="")
    sender_raw = models.CharField(
        _("Sender (raw)"), max_length=998, blank=True, default=""
    )
    subject = models.CharField(_("Subject"), max_length=998, blank=True, default="")
    subject_raw = models.CharField(
        _("Subject (raw)"), max_length=998, blank=True, default=""
    )
    date = models.DateTimeField(_("Date"), null=True, blank=True)
    body = models.TextField(_("Body"), blank=True, default="")
    link = models.URLField(_("Extracted link"), max_length=2048, blank=True, default="")
    read_by_me = models.BooleanField(_("Read by me"), default=False)
    fetched_at = models.DateTimeField(_("Fetched at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Mail message")
        verbose_name_plural = _("Mail messages")
        ordering = ["-date", "-fetched_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "message_id"],
                name="unique_message_id_per_source",
            ),
        ]

    def __str__(self):
        return self.subject or str(_("(no subject)"))


class CollectRule(models.Model):
    name = models.CharField(_("Name"), max_length=120, unique=True)
    enabled = models.BooleanField(_("Enabled"), default=True)
    logic_expr = models.CharField(
        _("Logic"),
        max_length=255,
        default="A",
        help_text=_("Boolean expression over condition letters with && || ! e.g. (A || B) && C"),
    )
    apply_to_existing = models.BooleanField(
        _("Apply to existing mails"),
        default=False,
        help_text=_(
            "On save, run the rule's actions on the currently matching "
            "mails; otherwise only newly collected mails trigger them."
        ),
    )
    symbol = models.CharField(_("Symbol"), max_length=40, default="star")
    color = models.CharField(_("Color (light)"), max_length=7, default="#c2a018")
    color_dark = models.CharField(
        _("Color (dark)"), max_length=7, default="#e6c65a"
    )
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Collect rule")
        verbose_name_plural = _("Collect rules")
        ordering = ["name"]

    def __str__(self):
        return self.name

    def matches_mail(self, mail):
        """Evaluate the rule's logic expression over its conditions,
        each condition identified by a letter (A, B, C, ...)."""
        from .logic import compile_expression, evaluate, LogicError

        conditions = list(self.conditions.all())
        if not conditions:
            return False
        values = {}
        for index, condition in enumerate(conditions):
            letter = chr(ord("A") + index)
            values[letter] = condition.matches_mail(mail)
        try:
            ast = compile_expression(self.logic_expr or "A")
        except LogicError:
            # Invalid stored expression: fall back to AND on all conditions.
            return all(values.values())
        return evaluate(ast, values)


class RuleCondition(models.Model):
    rule = models.ForeignKey(
        CollectRule,
        on_delete=models.CASCADE,
        related_name="conditions",
        verbose_name=_("Rule"),
    )
    target_field = models.CharField(
        _("Target field"), max_length=20, choices=TARGET_FIELD_CHOICES
    )
    match_type = models.CharField(
        _("Match type"), max_length=20, choices=MATCH_TYPE_CHOICES, default="contains"
    )
    value = models.CharField(_("Value"), max_length=255)
    negate = models.BooleanField(_("Negate (NOT)"), default=False)

    class Meta:
        verbose_name = _("Rule condition")
        verbose_name_plural = _("Rule conditions")
        ordering = ["pk"]

    def __str__(self):
        return f"{self.target_field} {self.match_type} {self.value}"

    def clean(self):
        if self.match_type == "regex":
            validate_regex(self.value)

    def matches_mail(self, mail):
        if self.negate:
            return not self.matches(mail)
        return self.matches(mail)

    def matches(self, mail):
        text = {
            "sender": mail.sender,
            "subject": mail.subject,
            "body": mail.body,
        }.get(self.target_field, "")
        if self.match_type == "regex":
            try:
                return re.search(self.value, text) is not None
            except re.error:
                return False
        return self.value.lower() in text.lower()


ACTION_TYPE_CHOICES = [
    ("mark_read", _("Read")),
    ("http_callback", _("Callback")),
]


class RuleAction(models.Model):
    rule = models.ForeignKey(
        CollectRule,
        on_delete=models.CASCADE,
        related_name="actions",
        verbose_name=_("Rule"),
    )
    action_type = models.CharField(
        _("Action"), max_length=20, choices=ACTION_TYPE_CHOICES, default="mark_read"
    )
    callback_url = models.URLField(
        _("Callback URL"), max_length=2048, blank=True, default=""
    )

    class Meta:
        verbose_name = _("Rule action")
        verbose_name_plural = _("Rule actions")
        ordering = ["pk"]

    def __str__(self):
        return self.get_action_type_display()

    def clean(self):
        if self.action_type == "http_callback" and not self.callback_url:
            raise models.base.ValidationError(
                _("A callback URL is required for this action.")
            )

    def execute(self, mail):
        """Run the action on a mail. Returns True on success."""
        if self.action_type == "mark_read":
            MailMessage.objects.filter(pk=mail.pk).update(read_by_me=True)
            mail.read_by_me = True
            return True
        if self.action_type == "http_callback":
            return send_callback(self, mail)
        return False


def send_callback(action, mail):
    """POST the decoded mail as JSON {sender, object, body} to the action
    callback URL. Standard library only; short timeout; errors swallowed
    at call sites."""
    import json
    import logging
    import urllib.request

    logger = logging.getLogger(__name__)
    logger.info(
        "send_callback: url=%r mail=%s", action.callback_url, mail.message_id
    )
    payload = json.dumps(
        {"sender": mail.sender, "object": mail.subject, "body": mail.body}
    ).encode("utf-8")
    request = urllib.request.Request(
        action.callback_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            ok = 200 <= response.status < 300
            logger.info(
                "send_callback result: url=%r status=%s ok=%s",
                action.callback_url, response.status, ok,
            )
            return ok
    except Exception as exc:
        logger.warning(
            "send_callback FAILED: url=%r mail=%s error=%s",
            action.callback_url, mail.message_id, exc,
        )
        return False


class RuleActionLog(models.Model):
    """Records that an action already ran for a mail, so callback
    actions are sent once per mail (first results on save, then only
    newly matching mails)."""

    action = models.ForeignKey(
        RuleAction,
        on_delete=models.CASCADE,
        related_name="logs",
        verbose_name=_("Action"),
    )
    mail = models.ForeignKey(
        MailMessage,
        on_delete=models.CASCADE,
        related_name="action_logs",
        verbose_name=_("Mail"),
    )
    executed_at = models.DateTimeField(_("Executed at"), auto_now_add=True)

    class Meta:
        verbose_name = _("Rule action log")
        verbose_name_plural = _("Rule action logs")
        constraints = [
            models.UniqueConstraint(
                fields=["action", "mail"], name="unique_action_mail"
            ),
        ]


def run_action_once(action, mail):
    """Execute the action unless it already ran for this mail.

    Returns True if it ran now, False if it was already executed (or
    failed: failures are not logged so they retry on the next pass).
    """
    import logging

    logger = logging.getLogger(__name__)
    if RuleActionLog.objects.filter(action=action, mail=mail).exists():
        logger.info(
            "run_action_once skipped (already logged): action=%s pk=%s "
            "url=%r mail=%s",
            action.action_type, action.pk, action.callback_url, mail.message_id,
        )
        return False
    ok = action.execute(mail)
    if ok:
        RuleActionLog.objects.create(action=action, mail=mail)
    else:
        logger.warning(
            "run_action_once FAILED (not logged, will retry): action=%s "
            "pk=%s url=%r mail=%s",
            action.action_type, action.pk, action.callback_url, mail.message_id,
        )
    return ok


class RuleMatch(models.Model):
    rule = models.ForeignKey(
        CollectRule,
        on_delete=models.CASCADE,
        related_name="matches",
        verbose_name=_("Rule"),
    )
    mail = models.ForeignKey(
        MailMessage,
        on_delete=models.CASCADE,
        related_name="rule_matches",
        verbose_name=_("Mail"),
    )
    matched_at = models.DateTimeField(_("Match date"), auto_now_add=True)

    class Meta:
        verbose_name = _("Rule match")
        verbose_name_plural = _("Rule matches")
        constraints = [
            models.UniqueConstraint(fields=["rule", "mail"], name="unique_rule_mail"),
        ]

    def __str__(self):
        return f"{self.rule} -> {self.mail}"
