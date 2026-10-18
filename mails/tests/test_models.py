import json
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from mails.models import (
    CollectRule,
    MailMessage,
    MailSource,
    RuleAction,
    RuleCondition,
    RuleMatch,
)


class MailSourceTests(TestCase):
    def test_str(self):
        source = MailSource.objects.create(
            name="Test", host="imap.example.com", username="u"
        )
        self.assertEqual(str(source), "Test")

    def test_interval_elapsed_when_never_fetched(self):
        source = MailSource.objects.create(
            name="Test", host="h", username="u", enabled=True
        )
        self.assertTrue(source.interval_elapsed)

    def test_interval_not_elapsed_when_recent(self):
        source = MailSource.objects.create(
            name="Test", host="h", username="u", fetch_frequency=15, enabled=True
        )
        source.last_fetch_at = timezone.now()
        self.assertFalse(source.interval_elapsed)

    def test_interval_elapsed_after_frequency(self):
        source = MailSource.objects.create(
            name="Test", host="h", username="u", fetch_frequency=15, enabled=True
        )
        source.last_fetch_at = timezone.now() - timedelta(minutes=16)
        self.assertTrue(source.interval_elapsed)

    def test_interval_never_elapsed_when_disabled(self):
        source = MailSource.objects.create(
            name="Test", host="h", username="u", enabled=False
        )
        self.assertFalse(source.interval_elapsed)


class MailMessageTests(TestCase):
    def setUp(self):
        self.source = MailSource.objects.create(
            name="Test", host="h", username="u"
        )

    def test_unique_message_id_per_source(self):
        MailMessage.objects.create(
            source=self.source, message_id="<1@example.com>"
        )
        with self.assertRaises(Exception):
            MailMessage.objects.create(
                source=self.source, message_id="<1@example.com>"
            )

    def test_same_message_id_allowed_across_sources(self):
        other = MailSource.objects.create(name="Other", host="h", username="u")
        MailMessage.objects.create(source=self.source, message_id="<1@example.com>")
        MailMessage.objects.create(source=other, message_id="<1@example.com>")
        self.assertEqual(MailMessage.objects.count(), 2)

    def test_str_falls_back_to_no_subject(self):
        mail = MailMessage.objects.create(
            source=self.source, message_id="<2@example.com>", subject=""
        )
        self.assertEqual(str(mail), "(no subject)")


def make_rule(name, target_field, match_type, value, enabled=True):
    rule = CollectRule.objects.create(name=name, enabled=enabled)
    RuleCondition.objects.create(
        rule=rule, target_field=target_field, match_type=match_type, value=value
    )
    return rule


class CollectRuleTests(TestCase):
    def make_mail(self, sender="", subject="", body=""):
        self.source = getattr(self, "source", None) or MailSource.objects.create(
            name="S", host="h", username="u"
        )
        return MailMessage(
            source=self.source,
            message_id="<x@y>",
            sender=sender,
            subject=subject,
            body=body,
        )

    def test_exact_match_sender(self):
        rule = make_rule("r", "sender", "contains", "alice@example.com")
        self.assertTrue(rule.matches_mail(self.make_mail(sender="alice@example.com")))
        self.assertTrue(rule.matches_mail(self.make_mail(sender="Alice <alice@example.com>")))
        self.assertFalse(rule.matches_mail(self.make_mail(sender="bob@example.com")))

    def test_exact_match_subject(self):
        rule = make_rule("r", "subject", "contains", "Hello")
        self.assertTrue(rule.matches_mail(self.make_mail(subject="Hello")))
        self.assertTrue(rule.matches_mail(self.make_mail(subject="hello world")))
        self.assertFalse(rule.matches_mail(self.make_mail(subject=" greeting ")))

    def test_exact_match_body(self):
        rule = make_rule("r", "body", "contains", "ping")
        self.assertTrue(rule.matches_mail(self.make_mail(body="ping")))
        self.assertTrue(rule.matches_mail(self.make_mail(body="a ping here\n")))

    def test_regex_match_subject(self):
        rule = make_rule("r", "subject", "regex", r"(?i)(job|offer)")
        self.assertTrue(rule.matches_mail(self.make_mail(subject="Great JOB offer!")))
        self.assertFalse(rule.matches_mail(self.make_mail(subject="Greetings")))

    def test_regex_match_sender(self):
        rule = make_rule("r", "sender", "regex", r"@family\.example$")
        self.assertTrue(rule.matches_mail(self.make_mail(sender="mom@family.example")))
        self.assertFalse(rule.matches_mail(self.make_mail(sender="mom@family.example.org")))

    def test_regex_validation_rejects_invalid(self):
        condition = RuleCondition(
            target_field="subject", match_type="regex", value="[unclosed"
        )
        with self.assertRaises(ValidationError):
            condition.clean()

    def test_regex_validation_accepts_valid(self):
        condition = RuleCondition(
            target_field="subject", match_type="regex", value=r"^Hello .*$"
        )
        condition.clean()

    def test_invalid_stored_regex_does_not_crash(self):
        rule = make_rule("r", "subject", "regex", "[unclosed")
        self.assertFalse(rule.matches_mail(self.make_mail(subject="anything")))

    def test_several_rules_can_match_one_mail(self):
        source = MailSource.objects.create(name="SrcMarkRead", host="h", username="u")
        mail = MailMessage.objects.create(
            source=source, message_id="<1@x>", sender="recruiter@corp.example",
            subject="Job offer",
        )
        r1 = make_rule("jobs", "subject", "regex", "(?i)job")
        r2 = make_rule("corp", "sender", "regex", r"corp\.example$")
        r3 = make_rule("news", "subject", "contains", "Newsletter")
        matched = [rule.name for rule in (r1, r2, r3) if rule.matches_mail(mail)]
        self.assertEqual(matched, ["jobs", "corp"])
        for rule in (r1, r2):
            RuleMatch.objects.create(rule=rule, mail=mail)
        self.assertEqual(mail.rule_matches.count(), 2)

    def test_rule_with_multiple_conditions_uses_and(self):
        rule = CollectRule.objects.create(
            name="and-rule", enabled=True, logic_expr="A AND B"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="regex", value="(?i)job"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="sender", match_type="regex",
            value=r"corp\.example$",
        )
        mail = self.make_mail(
            sender="recruiter@corp.example", subject="Job offer"
        )
        self.assertTrue(rule.matches_mail(mail))
        only_subject = self.make_mail(
            sender="someone@other.example", subject="Job offer"
        )
        self.assertFalse(rule.matches_mail(only_subject))

    def test_rule_with_or_operator(self):
        rule = CollectRule.objects.create(
            name="or-rule", logic_expr="A OR B"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="regex", value="(?i)job"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="sender", match_type="contains",
            value="mom@family.example",
        )
        job_mail = self.make_mail(sender="any@x", subject="a job")
        mom_mail = self.make_mail(sender="mom@family.example", subject="hello")
        none_mail = self.make_mail(sender="any@x", subject="hello")
        self.assertTrue(rule.matches_mail(job_mail))
        self.assertTrue(rule.matches_mail(mom_mail))
        self.assertFalse(rule.matches_mail(none_mail))

    def test_rule_logic_expression(self):
        rule = CollectRule.objects.create(
            name="expr-rule", logic_expr="(A OR B) AND C"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="regex", value="(?i)job"
        )
        RuleCondition.objects.create(
            rule=rule, target_field="sender", match_type="regex",
            value=r"corp\.example$",
        )
        RuleCondition.objects.create(
            rule=rule, target_field="body", match_type="regex", value="(?i)offer"
        )
        both = self.make_mail(
            sender="a@corp.example", subject="a job", body="see offer"
        )
        only_a = self.make_mail(
            sender="a@corp.example", subject="a job", body="nothing"
        )
        only_c = self.make_mail(
            sender="x@other.example", subject="hello", body="see offer"
        )
        self.assertTrue(rule.matches_mail(both))
        self.assertFalse(rule.matches_mail(only_a))
        self.assertFalse(rule.matches_mail(only_c))
        b_and_c = self.make_mail(
            sender="a@corp.example", subject="hello", body="see offer"
        )
        self.assertTrue(rule.matches_mail(b_and_c))

    def test_condition_negate(self):
        rule = CollectRule.objects.create(name="not-rule")
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="regex",
            value="(?i)newsletter", negate=True,
        )
        newsletter = self.make_mail(subject="Weekly newsletter")
        regular = self.make_mail(subject="a job")
        self.assertFalse(rule.matches_mail(newsletter))
        self.assertTrue(rule.matches_mail(regular))

    def test_action_mark_read(self):
        rule = CollectRule.objects.create(name="read-rule")
        RuleCondition.objects.create(
            rule=rule, target_field="subject", match_type="contains", value="job"
        )
        RuleAction.objects.create(rule=rule, action_type="mark_read")
        mail = self.make_mail(sender="a@b.c", subject="a job offer")
        MailMessage.objects.create(
            source=MailSource.objects.create(name="SrcMarkRead", host="h", username="u"),
            message_id="<mr@x>", sender="a@b.c", subject="a job offer",
        )
        stored = MailMessage.objects.get(message_id="<mr@x>")
        self.assertFalse(stored.read_by_me)
        rule.actions.first().execute(stored)
        stored.refresh_from_db()
        self.assertTrue(stored.read_by_me)

    def test_action_http_callback(self):
        from unittest import mock

        from mails.models import send_callback
        rule = CollectRule.objects.create(name="cb-rule")
        action = RuleAction.objects.create(
            rule=rule, action_type="http_callback",
            callback_url="https://hooks.example.com/mail",
        )
        mail = MailMessage.objects.create(
            source=MailSource.objects.create(name="SrcCallback", host="h", username="u"),
            message_id="<cb@x>", sender="Aleksandar <noreply@corp.example>",
            subject="A job offer", body="See https://example.com",
        )
        captured = {}
        class FakeResponse:
            status = 200
            def __enter__(self):
                return self
            def __exit__(self, *a):
                return False
        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["data"] = json.loads(req.data.decode("utf-8"))
            captured["headers"] = req.headers
            return FakeResponse()
        with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
            self.assertTrue(action.execute(mail))
        self.assertEqual(captured["url"], "https://hooks.example.com/mail")
        self.assertEqual(captured["data"], {
            "sender": "Aleksandar <noreply@corp.example>",
            "object": "A job offer",
            "body": "See https://example.com",
        })
        self.assertEqual(captured["headers"].get("Content-type"), "application/json")

    def test_rule_without_conditions_never_matches(self):
        rule = CollectRule.objects.create(name="empty", enabled=True)
        self.assertFalse(rule.matches_mail(self.make_mail(subject="anything")))

    def test_unique_rule_match(self):
        source = MailSource.objects.create(name="SrcMarkRead", host="h", username="u")
        mail = MailMessage.objects.create(
            source=source, message_id="<1@x>", subject="s"
        )
        rule = make_rule("r", "subject", "contains", "s")
        RuleMatch.objects.create(rule=rule, mail=mail)
        with self.assertRaises(Exception):
            RuleMatch.objects.create(rule=rule, mail=mail)
