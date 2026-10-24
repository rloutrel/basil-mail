import json

from django.test import TestCase

from mails.imap import apply_rules
from django.urls import reverse

from mails.models import CollectRule, MailMessage, MailSource, RuleCondition, RuleMatch


def create_source(name="Test"):
    return MailSource.objects.create(name=name, host="h", username="u")


def make_condition(rule, target_field, match_type, value):
    return RuleCondition.objects.create(
        rule=rule, target_field=target_field, match_type=match_type, value=value
    )


def action_management(prefix):
    return {
        "%s-TOTAL_FORMS" % prefix: "0",
        "%s-INITIAL_FORMS" % prefix: "0",
        "%s-MIN_NUM_FORMS" % prefix: "0",
        "%s-MAX_NUM_FORMS" % prefix: "1000",
    }


def create_mail(source, message_id, sender="", subject="", body=""):
    return MailMessage.objects.create(
        source=source, message_id=message_id, sender=sender, subject=subject,
        body=body,
    )


class MailListViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source1 = create_source("Work")
        cls.source2 = create_source("Personal")
        cls.job_rule = CollectRule.objects.create(name="Job offers")
        make_condition(cls.job_rule, "subject", "regex", "(?i)job")
        cls.personal_rule = CollectRule.objects.create(name="Personal")
        make_condition(cls.personal_rule, "sender", "regex", r"@family\.example$")
        cls.m1 = create_mail(cls.source1, "<1@x>", sender="recruiter@corp.example",
                             subject="Job offer", body="Hello")
        cls.m2 = create_mail(cls.source2, "<2@x>", sender="mom@family.example",
                             subject="Dinner", body="See you")
        cls.m3 = create_mail(cls.source1, "<3@x>", sender="newsletter@example.com",
                             subject="Weekly news", body="Read all")
        RuleMatch.objects.create(rule=cls.job_rule, mail=cls.m1)
        RuleMatch.objects.create(rule=cls.personal_rule, mail=cls.m2)

    def test_list_shows_all_mails(self):
        response = self.client.get(reverse("mails:mail_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Job offer")
        self.assertContains(response, "Dinner")
        self.assertContains(response, "Weekly news")

    def test_unsorted_mails_badge_and_classes(self):
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("mail-matched", html)
        self.assertIn("mail-unsorted", html)
        self.assertIn("Unsorted", html)

    def test_filter_by_rule(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"rule": self.job_rule.pk})
        self.assertContains(response, "Job offer")
        self.assertNotContains(response, "Dinner")

    def test_filter_unsorted(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"rule": "unsorted"})
        mails = list(response.context["mails"])
        self.assertEqual([m.pk for m in mails], [self.m3.pk])

    def test_filter_by_source(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"source": self.source2.pk})
        self.assertContains(response, "Dinner")
        self.assertNotContains(response, "Weekly news")

    def test_filter_by_sender_contains_case_insensitive(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"sender": "MOM@"})
        mails = list(response.context["mails"])
        self.assertEqual([m.pk for m in mails], [self.m2.pk])

    def test_filter_by_subject_contains_case_insensitive(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"subject": "WEEKLY"})
        self.assertContains(response, "Weekly news")
        self.assertNotContains(response, "Dinner")

    def test_filters_combined_with_and_logic(self):
        url = reverse("mails:mail_list")
        response = self.client.get(url, {"sender": "corp", "subject": "job"})
        self.assertContains(response, "Job offer")
        self.assertNotContains(response, "Dinner")
        self.assertNotContains(response, "Weekly news")

    def test_filters_combined_no_result(self):
        url = reverse("mails:mail_list")
        response = self.client.get(
            url, {"sender": "corp", "subject": "dinner"}
        )
        self.assertContains(response, "No mails match")

    def test_filters_preserved_across_pagination(self):
        source = create_source("Bulk")
        for i in range(30):
            mail = create_mail(source, f"<bulk{i}@x>", sender="bulk@example.com",
                               subject=f"Job {i}")
            RuleMatch.objects.create(rule=self.job_rule, mail=mail)
        url = reverse("mails:mail_list")
        response = self.client.get(
            url, {"sender": "bulk", "rule": self.job_rule.pk, "page": 2}
        )
        self.assertContains(response, "sender=bulk")
        self.assertContains(response, f"rule={self.job_rule.pk}")
        self.assertEqual(len(response.context["mails"]), 5)

    def test_pagination_page_size(self):
        source = create_source("Bulk2")
        for i in range(30):
            create_mail(source, f"<b2_{i}@x>", sender="x@example.com", subject=f"S{i}")
        response = self.client.get(reverse("mails:mail_list"))
        self.assertEqual(len(response.context["mails"]), 25)
        self.assertEqual(response.context["page"].paginator.num_pages, 2)

    def test_columns_attribute_markers(self):
        """Table headers and cells carry stable data-col keys for the
        show/hide/reorder/resize column manager."""
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        for key in ("mailbox", "sender", "subject", "date", "rules"):
            self.assertIn('data-col="%s"' % key, html)

    def test_columns_toolbar_present(self):
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("data-col-button", html)
        self.assertIn("data-col-menu", html)

    def test_mail_table_partial(self):
        response = self.client.get(reverse("mails:mail_table"))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("<html", response.content.decode())

    def test_mail_detail_contains_body_and_link(self):
        self.m3.body = "Read https://example.com/article now"
        self.m3.link = "https://example.com/article"
        self.m3.save()
        response = self.client.get(reverse("mails:mail_detail", args=[self.m3.pk]))
        self.assertContains(response, "Read https://example.com/article")
        self.assertContains(response, 'href="https://example.com/article"')

    def test_mail_table_rows_expand_with_secondary_detail_row(self):
        response = self.client.get(reverse("mails:mail_table"))
        html = response.content.decode()
        self.assertIn("toggleMailRow(%d)" % self.m1.pk, html)
        self.assertIn('id="mail-row-%d"' % self.m1.pk, html)
        self.assertIn('data-mail-url="/mails/%d/"' % self.m1.pk, html)
        self.assertIn('id="mail-detail-%d"' % self.m1.pk, html)
        self.assertIn('id="mail-body-%d"' % self.m1.pk, html)
        self.assertIn('hidden', html)
        self.assertNotIn("__openMail", html)
        self.assertNotIn("modal", html)

    def test_mail_detail_row_content_has_no_subject_heading(self):
        response = self.client.get(reverse("mails:mail_detail", args=[self.m3.pk]))
        self.assertNotContains(response, "<h2>")
        self.assertContains(response, "mail-detail-body")

    def test_fetch_now_returns_202(self):
        response = self.client.post(reverse("mails:fetch_now"))
        self.assertEqual(response.status_code, 202)

    def test_fetch_now_accepts_htmx_with_csrf_token(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        client.get(reverse("mails:mail_list"))
        token = client.cookies["csrftoken"].value
        response = client.post(
            reverse("mails:fetch_now"),
            HTTP_X_CSRFTOKEN=token,
        )
        self.assertEqual(response.status_code, 202)

    def test_fetch_now_rejected_without_csrf_token(self):
        from django.test import Client

        client = Client(enforce_csrf_checks=True)
        response = client.post(reverse("mails:fetch_now"))
        self.assertEqual(response.status_code, 403)



class LanguageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = create_source("Work")

    def test_default_english(self):
        response = self.client.get(reverse("mails:mail_list"))
        self.assertContains(response, "Fetch now")

    def test_browser_language_negotiation_de(self):
        response = self.client.get(
            reverse("mails:mail_list"), headers={"Accept-Language": "de-DE,de;q=0.9"}
        )
        self.assertContains(response, "Jetzt abrufen")

    def test_browser_language_negotiation_fr(self):
        response = self.client.get(
            reverse("mails:mail_list"), headers={"Accept-Language": "fr-FR,fr;q=0.9"}
        )
        self.assertContains(response, "Récupérer maintenant")

    def test_unknown_language_falls_back_to_default(self):
        response = self.client.get(
            reverse("mails:mail_list"), headers={"Accept-Language": "it-IT,it;q=0.9"}
        )
        self.assertContains(response, "Fetch now")

    def test_set_language_switches_session_language(self):
        from django.conf import settings

        response = self.client.post(
            "/i18n/setlang/", {"language": "de", "next": "/"}
        )
        self.assertEqual(response.status_code, 302)
        response = self.client.get(reverse("mails:mail_list"))
        self.assertContains(response, "Jetzt abrufen")

    def test_language_dropdown_lists_available_languages(self):
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn('name="language"', html)
        for option in ("de", "fr", "en"):
            self.assertIn('value="%s"' % option, html)


class ConfigViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.source = create_source("Work")
        cls.rule = CollectRule.objects.create(name="Jobs")
        make_condition(cls.rule, "subject", "regex", "(?i)job")
        mail = create_mail(cls.source, "<1@x>", subject="a job")
        RuleMatch.objects.create(rule=cls.rule, mail=mail)

    def test_config_lists_sources_and_rules(self):
        response = self.client.get(reverse("mails:config"))
        self.assertContains(response, "Work")
        self.assertContains(response, "Jobs")

    def test_rule_count_links_to_filtered_mails(self):
        response = self.client.get(reverse("mails:config"))
        html = response.content.decode()
        # the matching-mails badge-link is gone from the rule cards
        self.assertNotIn("mails/?rule=", html)
        # the count pill remains
        self.assertIn("logic-count", html)

    def test_source_create(self):
        url = reverse("mails:source_create")
        response = self.client.post(url, {
            "source-new-name": "New", "source-new-host": "imap.example.com",
            "source-new-port": 993, "source-new-use_ssl": "on",
            "source-new-username": "u", "source-new-password": "p",
            "source-new-folder": "INBOX", "source-new-fetch_frequency": 10,
            "source-new-enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "config-body")
        self.assertTrue(MailSource.objects.filter(name="New").exists())

    def test_source_update(self):
        url = reverse("mails:source_update", args=[self.source.pk])
        response = self.client.post(url, {
            "source-%d-name" % self.source.pk: "Work",
            "source-%d-host" % self.source.pk: "imap2.example.com",
            "source-%d-port" % self.source.pk: 143,
            "source-%d-use_ssl" % self.source.pk: "",
            "source-%d-username" % self.source.pk: "u",
            "source-%d-password" % self.source.pk: "p",
            "source-%d-folder" % self.source.pk: "INBOX",
            "source-%d-fetch_frequency" % self.source.pk: 5,
            "source-%d-enabled" % self.source.pk: "on",
        })
        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(self.source.host, "imap2.example.com")
        self.assertFalse(self.source.use_ssl)

    def test_source_form_shows_symbol_and_color_pickers(self):
        response = self.client.get(reverse("mails:source_create"))
        html = response.content.decode()
        self.assertIn("symbol-picker", html)
        self.assertIn("color-picker", html)
        self.assertIn("icon-light", html)

    def test_source_create_defaults_symbol_and_color(self):
        url = reverse("mails:source_create")
        response = self.client.post(url, {
            "source-new-name": "NoSymbol", "source-new-host": "imap.example.com",
            "source-new-port": 993, "source-new-use_ssl": "on",
            "source-new-username": "u", "source-new-password": "p",
            "source-new-folder": "INBOX", "source-new-fetch_frequency": 10,
            "source-new-enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        source = MailSource.objects.get(name="NoSymbol")
        self.assertEqual(source.symbol, "envelope")
        self.assertEqual(source.color, "#2f6f4f")

    def test_source_create_form_shows_test_connection_button(self):
        response = self.client.get(reverse("mails:source_create"))
        self.assertContains(response, "Test connection")
        self.assertContains(response, reverse("mails:source_test_new"))
        self.assertContains(response, "test-result-new")

    def test_source_test_new_connection_success(self):
        from unittest import mock
        from mails.tests.test_imap import FakeIMAP
        with mock.patch("imaplib.IMAP4_SSL", return_value=FakeIMAP([])):
            response = self.client.post(reverse("mails:source_test_new"), {
                "source-new-name": "New", "source-new-host": "imap.example.com",
                "source-new-port": 993, "source-new-use_ssl": "on",
                "source-new-username": "u", "source-new-password": "p",
                "source-new-folder": "INBOX", "source-new-fetch_frequency": 10,
            })
        self.assertContains(response, "Connection succeeded")
        self.assertContains(response, "test-result ok")
        self.assertFalse(MailSource.objects.filter(name="New").exists())

    def test_source_test_new_connection_failure(self):
        from unittest import mock
        with mock.patch("imaplib.IMAP4_SSL", side_effect=OSError("refused")):
            response = self.client.post(reverse("mails:source_test_new"), {
                "source-new-name": "New", "source-new-host": "imap.example.com",
                "source-new-port": 993, "source-new-use_ssl": "on",
                "source-new-username": "u", "source-new-password": "p",
                "source-new-folder": "INBOX", "source-new-fetch_frequency": 10,
            })
        self.assertContains(response, "Connection failed")
        self.assertContains(response, "refused")

    def test_source_test_new_invalid_form(self):
        response = self.client.post(reverse("mails:source_test_new"), {})
        self.assertContains(response, "Fix the form errors first")
        self.assertContains(response, "test-result error")

    def test_source_create_with_symbol_and_color(self):
        url = reverse("mails:source_create")
        response = self.client.post(url, {
            "source-new-name": "SymSource", "source-new-host": "imap.example.com",
            "source-new-port": 993, "source-new-use_ssl": "on",
            "source-new-username": "u", "source-new-password": "p",
            "source-new-folder": "INBOX", "source-new-symbol": "briefcase",
            "source-new-color": "#1f6fb2", "source-new-color_dark": "#74b3ef",
            "source-new-fetch_frequency": 10, "source-new-enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        source = MailSource.objects.get(name="SymSource")
        self.assertEqual(source.symbol, "briefcase")
        self.assertEqual(source.color, "#1f6fb2")

    def test_source_create_with_color_pair(self):
        url = reverse("mails:source_create")
        response = self.client.post(url, {
            "source-new-name": "PairSource", "source-new-host": "imap.example.com",
            "source-new-port": 993, "source-new-use_ssl": "on",
            "source-new-username": "u", "source-new-password": "p",
            "source-new-folder": "INBOX", "source-new-symbol": "envelope",
            "source-new-color": "#1f6fb2", "source-new-color_dark": "#74b3ef",
            "source-new-fetch_frequency": 10, "source-new-enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        source = MailSource.objects.get(name="PairSource")
        self.assertEqual(source.color, "#1f6fb2")
        self.assertEqual(source.color_dark, "#74b3ef")

    def test_existing_sources_get_dark_color_default(self):
        self.source.refresh_from_db()
        self.assertRegex(self.source.color_dark, r"^#[0-9a-fA-F]{6}$")

    def test_symbol_picker_renders_dual_light_dark(self):
        response = self.client.get(reverse("mails:source_create"))
        html = response.content.decode()
        self.assertIn("symbol-pair", html)
        self.assertIn('class="icon-light"', html)
        self.assertIn('class="icon-dark"', html)

    def test_color_picker_shows_pairs(self):
        response = self.client.get(reverse("mails:source_create"))
        html = response.content.decode()
        self.assertIn("color-pair", html)
        self.assertIn("swatch-light", html)
        self.assertIn("swatch-dark", html)
        self.assertIn("data-value-dark", html)

    def test_mail_table_uses_theme_aware_colors(self):
        create_mail(self.source, "<pair1@x>", subject="Pair mail")
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("--source-color:", html)
        self.assertIn("--source-color-dark:", html)

    def test_source_create_rejects_invalid_color(self):
        url = reverse("mails:source_create")
        response = self.client.post(url, {
            "source-new-name": "BadColor", "source-new-host": "imap.example.com",
            "source-new-port": 993, "source-new-use_ssl": "on",
            "source-new-username": "u", "source-new-password": "p",
            "source-new-folder": "INBOX", "source-new-symbol": "envelope",
            "source-new-color": "green", "source-new-fetch_frequency": 10,
            "source-new-enabled": "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MailSource.objects.filter(name="BadColor").exists())

    def test_existing_sources_get_default_symbol_and_color(self):
        """Migration default: sources configured before this feature have
        a valid symbol/color combination."""
        self.source.refresh_from_db()
        self.assertIn(self.source.symbol, MailSource.SYMBOLS)
        self.assertRegex(self.source.color, r"^#[0-9a-fA-F]{6}$")

    def test_mail_table_shows_source_symbol(self):
        create_mail(self.source, "<sym1@x>", subject="Symbol mail")
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("source-symbol", html)
        self.assertIn('title="%s"' % self.source.name, html)

    def test_rules_column_renders_colored_circles(self):
        create_mail(self.source, "<dot1@x>", subject="a job offer")
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("rule-dot", html)
        self.assertIn("--dot: %s" % self.rule.color, html)
        self.assertIn("bi-%s" % self.rule.symbol, html)

    def test_mail_table_renders_inline_bootstrap_icon(self):
        create_mail(self.source, "<icon1@x>", subject="Icon mail")
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn("<svg xmlns", html)
        self.assertIn("bi-envelope", html)
        self.assertNotIn("&lt;svg", html)

    def test_mailbox_column_is_empty_header(self):
        response = self.client.get(reverse("mails:mail_list"))
        html = response.content.decode()
        self.assertIn('<th data-col="mailbox"', html)

    def test_source_rename_endpoint(self):
        url = reverse("mails:source_rename", args=[self.source.pk])
        response = self.client.post(url, {"name": "Renamed"})
        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, "Renamed")

    def test_rule_rename_endpoint(self):
        url = reverse("mails:rule_rename", args=[self.rule.pk])
        response = self.client.post(url, {"name": "RenamedRule"})
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.name, "RenamedRule")

    def test_rename_empty_name_keeps_original(self):
        url = reverse("mails:source_rename", args=[self.source.pk])
        original = self.source.name
        self.client.post(url, {"name": ""})
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, original)

    def test_source_update_blank_password_keeps_old(self):
        url = reverse("mails:source_update", args=[self.source.pk])
        old = self.source.password
        self.client.post(url, {
            "source-%d-name" % self.source.pk: self.source.name,
            "source-%d-host" % self.source.pk: self.source.host,
            "source-%d-port" % self.source.pk: self.source.port,
            "source-%d-use_ssl" % self.source.pk: "on",
            "source-%d-username" % self.source.pk: self.source.username,
            "source-%d-password" % self.source.pk: "",
            "source-%d-folder" % self.source.pk: self.source.folder,
            "source-%d-fetch_frequency" % self.source.pk: 15,
        })
        self.source.refresh_from_db()
        self.assertEqual(self.source.password, old)

    def test_source_password_not_rendered_in_html(self):
        MailSource.objects.filter(pk=self.source.pk).update(password="secret123")
        html = self.client.get(reverse("mails:config")).content.decode()
        self.assertNotIn("secret123", html)

    def test_source_update_returns_only_card(self):
        url = reverse("mails:source_update", args=[self.source.pk])
        other = create_source("OtherBox")
        response = self.client.post(url, {
            "source-%d-name" % self.source.pk: self.source.name,
            "source-%d-host" % self.source.pk: "newhost.example.com",
            "source-%d-port" % self.source.pk: 993,
            "source-%d-use_ssl" % self.source.pk: "on",
            "source-%d-username" % self.source.pk: self.source.username,
            "source-%d-password" % self.source.pk: "",
            "source-%d-folder" % self.source.pk: self.source.folder,
            "source-%d-fetch_frequency" % self.source.pk: 15,
        })
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertEqual(html.count('id="source-'), 1)
        self.assertNotIn("OtherBox", html)
        self.assertNotIn('id="rules"', html)
        self.source.refresh_from_db()
        self.assertEqual(self.source.host, "newhost.example.com")

    def test_source_toggle_endpoint(self):
        url = reverse("mails:source_toggle", args=[self.source.pk])
        was = self.source.enabled
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(self.source.enabled, not was)
        self.assertContains(response, "summary-switch")
        # surgical swap: only the affected source card, no rule cards
        self.assertContains(response, "id=\"source-%d\"" % self.source.pk)
        self.assertNotContains(response, "id=\"rule-")

    def test_rule_toggle_endpoint_reapplies_when_enabling(self):
        mail = create_mail(self.source, "<toggle1@x>", subject="a job for you")
        url = reverse("mails:rule_toggle", args=[self.rule.pk])
        self.rule.enabled = False
        self.rule.save()
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertTrue(self.rule.enabled)
        self.assertTrue(
            RuleMatch.objects.filter(rule=self.rule, mail=mail).exists()
        )

    def test_source_delete(self):
        url = reverse("mails:source_delete", args=[self.source.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MailSource.objects.filter(pk=self.source.pk).exists())

    def test_source_test_connection_success(self):
        from unittest import mock
        from mails.tests.test_imap import FakeIMAP
        with mock.patch("imaplib.IMAP4_SSL", return_value=FakeIMAP([])):
            response = self.client.post(
                reverse("mails:source_test", args=[self.source.pk])
            )
        self.assertContains(response, "Connection succeeded")
        self.assertContains(response, "test-result ok")

    def test_source_test_connection_failure(self):
        from unittest import mock
        with mock.patch("imaplib.IMAP4_SSL", side_effect=OSError("refused")):
            response = self.client.post(
                reverse("mails:source_test", args=[self.source.pk])
            )
        self.assertContains(response, "Connection failed")
        self.assertContains(response, "refused")

    def test_rule_create_valid_regex(self):
        url = reverse("mails:rule_create")
        response = self.client.post(url, {
            "rule-new-name": "NewRule",
            "rule-new-conditions-TOTAL_FORMS": "1",
            "rule-new-conditions-INITIAL_FORMS": "0",
            "rule-new-conditions-MIN_NUM_FORMS": "1",
            "rule-new-conditions-MAX_NUM_FORMS": "1000",
            **action_management("rule-new-actions"),
            "rule-new-conditions-0-target_field": "subject",
            "rule-new-conditions-0-match_type": "regex",
            "rule-new-conditions-0-value": "(?i)hello",
            "rule-new-conditions-0-negate": "",
            "rule-new-logic_expr": "A",
        })
        self.assertEqual(response.status_code, 200)
        rule = CollectRule.objects.get(name="NewRule")
        self.assertEqual(rule.conditions.count(), 1)
        self.assertEqual(rule.conditions.first().value, "(?i)hello")

    def test_rule_create_invalid_regex_shows_inline_error(self):
        url = reverse("mails:rule_create")
        response = self.client.post(url, {
            "rule-new-name": "BadRule",
            "rule-new-conditions-TOTAL_FORMS": "1",
            "rule-new-conditions-INITIAL_FORMS": "0",
            "rule-new-conditions-MIN_NUM_FORMS": "1",
            "rule-new-conditions-MAX_NUM_FORMS": "1000",
            **action_management("rule-new-actions"),
            "rule-new-conditions-0-target_field": "subject",
            "rule-new-conditions-0-match_type": "regex",
            "rule-new-conditions-0-value": "[unclosed",
            "rule-new-conditions-0-negate": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invalid regular expression")
        self.assertFalse(CollectRule.objects.filter(name="BadRule").exists())

    def test_rule_update(self):
        url = reverse("mails:rule_update", args=[self.rule.pk])
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: "Jobs",
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-conditions-0-id" % self.rule.pk:
                self.rule.conditions.first().pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "body",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "contains",
            "rule-%d-conditions-0-value" % self.rule.pk: "job",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
            "rule-%d-logic_expr" % self.rule.pk: "A",
        })
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        condition = self.rule.conditions.first()
        self.assertEqual(condition.target_field, "body")
        self.assertEqual(condition.match_type, "contains")

    def test_new_rule_applies_backward_to_existing_mails(self):
        create_mail(self.source, "<retro1@x>", subject="New job opportunity")
        create_mail(self.source, "<retro2@x>", subject="Lunch plans")
        url = reverse("mails:rule_create")
        response = self.client.post(url, {
            "rule-new-name": "RetroJobs",
            "rule-new-conditions-TOTAL_FORMS": "1",
            "rule-new-conditions-INITIAL_FORMS": "0",
            "rule-new-conditions-MIN_NUM_FORMS": "1",
            "rule-new-conditions-MAX_NUM_FORMS": "1000",
            **action_management("rule-new-actions"),
            "rule-new-conditions-0-target_field": "subject",
            "rule-new-conditions-0-match_type": "regex",
            "rule-new-conditions-0-value": "(?i)job",
            "rule-new-conditions-0-negate": "",
            "rule-new-logic_expr": "A",
            "rule-new-conditions-0-negate": "",
        })
        self.assertEqual(response.status_code, 200)
        rule = CollectRule.objects.get(name="RetroJobs")
        matched = set(
            RuleMatch.objects.filter(rule=rule)
            .values_list("mail__message_id", flat=True)
        )
        self.assertIn("<retro1@x>", matched)
        self.assertNotIn("<retro2@x>", matched)

    def test_updated_rule_applies_backward(self):
        mail = create_mail(self.source, "<retro3@x>", body="hiring soon")
        url = reverse("mails:rule_update", args=[self.rule.pk])
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-conditions-0-id" % self.rule.pk:
                self.rule.conditions.first().pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "body",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
            "rule-%d-conditions-0-value" % self.rule.pk: "hiring",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
            "rule-%d-logic_expr" % self.rule.pk: "A",
        })
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertTrue(
            RuleMatch.objects.filter(rule=self.rule, mail=mail).exists()
        )

    def test_disabled_rule_not_reapplied(self):
        create_mail(self.source, "<retro4@x>", subject="a job again")
        url = reverse("mails:rule_update", args=[self.rule.pk])
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-target_field" % self.rule.pk: "subject",
            "rule-%d-match_type" % self.rule.pk: "regex",
            "rule-%d-value" % self.rule.pk: "(?i)again",
            "rule-%d-enabled" % self.rule.pk: "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            RuleMatch.objects.filter(
                rule=self.rule, mail__message_id="<retro4@x>"
            ).exists()
        )

    def test_rule_delete_returns_config_body(self):
        other = CollectRule.objects.create(name="OtherRule")
        make_condition(other, "subject", "exact", "x")
        url = reverse("mails:rule_delete", args=[self.rule.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "config-body")
        self.assertContains(response, "OtherRule")
        self.assertFalse(
            CollectRule.objects.filter(pk=self.rule.pk).exists()
        )
        self.assertTrue(CollectRule.objects.filter(pk=other.pk).exists())

    def test_rule_icon_autosave_with_extra_form_saves(self):
        """Browser flow: formset posts initial + empty extra row, with the
        condition id rendered as hidden input."""
        cond = self.rule.conditions.first()
        url = reverse("mails:rule_update", args=[self.rule.pk])
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-logic_expr" % self.rule.pk: "A",
            "rule-%d-symbol" % self.rule.pk: "heart",
            "rule-%d-color" % self.rule.pk: "#b2531f",
            "rule-%d-color_dark" % self.rule.pk: "#f0a35e",
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-conditions-0-id" % self.rule.pk: cond.pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
            "rule-%d-conditions-0-value" % self.rule.pk: "(?i)job",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
            "rule-%d-conditions-1-target_field" % self.rule.pk: "",
            "rule-%d-conditions-1-match_type" % self.rule.pk: "contains",
            "rule-%d-conditions-1-value" % self.rule.pk: "",
        })
        self.assertEqual(response.status_code, 200)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.symbol, "heart")
        self.assertEqual(self.rule.color, "#b2531f")
        self.assertEqual(self.rule.color_dark, "#f0a35e")
        self.assertEqual(self.rule.conditions.count(), 1)

    def test_rule_card_renders_condition_id_input(self):
        html = self.client.get(reverse("mails:config")).content.decode()
        cond = self.rule.conditions.first()
        self.assertIn(
            'name="rule-%d-conditions-0-id"' % self.rule.pk, html
        )
        self.assertIn('value="%d"' % cond.pk, html)

    def test_rule_update_error_returns_card_only(self):
        url = reverse("mails:rule_update", args=[self.rule.pk])
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-logic_expr" % self.rule.pk: "A",
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-conditions-0-id" % self.rule.pk:
                self.rule.conditions.first().pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
            "rule-%d-conditions-0-value" % self.rule.pk: "[unclosed",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
        })
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertNotIn('id="sources"', html)
        self.assertEqual(html.count('id="rule-'), 1)
        self.assertIn("Invalid regular expression", html)

    def test_rule_icon_autosave_updates_own_card(self):
        url = reverse("mails:rule_update", args=[self.rule.pk])
        other = CollectRule.objects.create(name="OtherRule")
        make_condition(other, "subject", "exact", "y")
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-logic_expr" % self.rule.pk: "A",
            "rule-%d-symbol" % self.rule.pk: "heart",
            "rule-%d-color" % self.rule.pk: "#b21f4f",
            "rule-%d-color_dark" % self.rule.pk: "#f280a8",
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-conditions-0-id" % self.rule.pk:
                self.rule.conditions.first().pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
            "rule-%d-conditions-0-value" % self.rule.pk: "(?i)job",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
        })
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("bi-heart", html)
        self.assertEqual(html.count("id=\"rule-"), 1)
        self.assertNotIn("OtherRule", html)
        self.rule.refresh_from_db()
        self.assertEqual(self.rule.symbol, "heart")

    def test_sender_suggestions_rendered(self):
        MailMessage.objects.create(
            source=self.source, message_id="<s1@x>",
            sender="noreply@corp.example", subject="a",
        )
        MailMessage.objects.create(
            source=self.source, message_id="<s2@x>",
            sender="noreply@corp.example", subject="b",
        )
        MailMessage.objects.create(
            source=self.source, message_id="<s3@x>",
            sender="mom@family.example", subject="c",
        )
        html = self.client.get(reverse("mails:config")).content.decode()
        i = html.find("<datalist")
        block = html[i:html.find("</datalist>", i)]
        self.assertEqual(block.count("<option"), 2)
        self.assertLess(
            block.find("noreply@corp.example"),
            block.find("mom@family.example"),
        )

    def test_rule_logic_builder_buttons(self):
        make_condition(self.rule, "body", "contains", "offer")
        html = self.client.get(reverse("mails:config")).content.decode()
        i = html.find('id="rule-%d"' % self.rule.pk)
        chunk = html[i:html.find("</details>", i)]
        # letters are buttons on the condition rows
        self.assertIn(
            'class="condition-letter logic-btn"', chunk
        )
        self.assertIn('data-insert="A"', chunk)
        self.assertIn('data-insert="B"', chunk)
        # sign buttons in the logic bar
        self.assertIn('data-insert="&&"', chunk)
        self.assertIn('data-insert="||"', chunk)
        self.assertIn('data-insert="!"', chunk)
        self.assertIn('data-insert="("', chunk)
        self.assertIn('data-insert=")"', chunk)
        self.assertIn("logic-clear", chunk)
        # name edited via summary: no visible name input in the card
        self.assertNotIn(
            'type="text" name="rule-%d-name"' % self.rule.pk, chunk
        )
        self.assertIn(
            'type="hidden" name="rule-%d-name"' % self.rule.pk, chunk
        )

    def test_reapply_removes_stale_matches(self):
        from mails.imap import reapply_rule

        # Give the rule a second condition so A OR B is meaningful
        make_condition(self.rule, "sender", "contains", "family.example")
        # (A || B): matches either
        self.rule.logic_expr = "A OR B"
        self.rule.save()
        job_mail = create_mail(self.source, "<stale1@x>", subject="a job offer")
        other_mail = create_mail(
            self.source, "<stale2@x>", sender="x@family.example", subject="hello"
        )
        reapply_rule(self.rule)
        self.assertEqual(
            set(RuleMatch.objects.filter(rule=self.rule)
                .values_list("mail__message_id", flat=True)),
            {"<1@x>", "<stale1@x>", "<stale2@x>"},
        )
        # note: "<1@x>" matches A (subject job)
        # Now tighten to (A && B): stale matches must be removed
        self.rule.logic_expr = "A AND B"
        self.rule.save()
        reapply_rule(self.rule)
        remaining = set(
            RuleMatch.objects.filter(rule=self.rule)
            .values_list("mail__message_id", flat=True)
        )
        self.assertNotIn("<stale1@x>", remaining)
        self.assertNotIn("<stale2@x>", remaining)

    def test_rule_with_actions_crud(self):
        from mails.models import RuleAction

        url = reverse("mails:rule_create")
        response = self.client.post(url, {
            "rule-new-name": "ActionRule",
            "rule-new-logic_expr": "A",
            "rule-new-symbol": "star",
            "rule-new-color": "#c2a018",
            "rule-new-color_dark": "#e6c65a",
            "rule-new-conditions-TOTAL_FORMS": "1",
            "rule-new-conditions-INITIAL_FORMS": "0",
            "rule-new-conditions-MIN_NUM_FORMS": "1",
            "rule-new-conditions-MAX_NUM_FORMS": "1000",
            "rule-new-conditions-0-target_field": "subject",
            "rule-new-conditions-0-match_type": "contains",
            "rule-new-conditions-0-value": "test",
            "rule-new-conditions-0-negate": "",
            **action_management("rule-new-actions"),
            "rule-new-actions-TOTAL_FORMS": "2",
            "rule-new-actions-INITIAL_FORMS": "0",
            "rule-new-actions-0-action_type": "mark_read",
            "rule-new-actions-0-callback_url": "",
            "rule-new-actions-1-action_type": "http_callback",
            "rule-new-actions-1-callback_url": "https://hooks.example.com/x",
        })
        self.assertEqual(response.status_code, 200)
        rule = CollectRule.objects.get(name="ActionRule")
        self.assertEqual(rule.actions.count(), 2)
        types = set(rule.actions.values_list("action_type", flat=True))
        self.assertEqual(types, {"mark_read", "http_callback"})

    def test_rule_action_requires_callback_url(self):
        url = reverse("mails:rule_create")
        response = self.client.post(url, {
            "rule-new-name": "BadActionRule",
            "rule-new-logic_expr": "A",
            "rule-new-conditions-TOTAL_FORMS": "1",
            "rule-new-conditions-INITIAL_FORMS": "0",
            "rule-new-conditions-MIN_NUM_FORMS": "1",
            "rule-new-conditions-MAX_NUM_FORMS": "1000",
            "rule-new-conditions-0-target_field": "subject",
            "rule-new-conditions-0-match_type": "contains",
            "rule-new-conditions-0-value": "x",
            "rule-new-conditions-0-negate": "",
            **action_management("rule-new-actions"),
            "rule-new-actions-TOTAL_FORMS": "1",
            "rule-new-actions-INITIAL_FORMS": "0",
            "rule-new-actions-0-action_type": "http_callback",
            "rule-new-actions-0-callback_url": "",
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            CollectRule.objects.filter(name="BadActionRule").exists()
        )

    def test_apply_to_existing_option(self):
        from mails.models import RuleAction, RuleActionLog, run_action_once

        from mails.imap import reapply_rule

        # a mail already stored that matches the rule
        mail = create_mail(self.source, "<exist@x>", subject="a job offer")
        action = RuleAction.objects.create(
            rule=self.rule, action_type="mark_read"
        )
        # Option OFF (default): saving does not run actions on existing mails
        self.rule.apply_to_existing = False
        self.rule.save()
        reapply_rule(self.rule)
        mail.refresh_from_db()
        self.assertFalse(mail.read_by_me)
        self.assertEqual(RuleActionLog.objects.count(), 0)
        # Option ON: saving runs actions on the currently matching mails
        self.rule.apply_to_existing = True
        self.rule.save()
        reapply_rule(self.rule)
        mail.refresh_from_db()
        self.assertTrue(mail.read_by_me)
        # both matching mails ("<1@x>" and "<exist@x>") got the action
        self.assertEqual(RuleActionLog.objects.count(), 2)
        # A second save does not duplicate (log guards once-per-mail)
        reapply_rule(self.rule)
        self.assertEqual(RuleActionLog.objects.count(), 2)

    def test_rule_action_delete(self):
        from mails.models import RuleAction

        action = RuleAction.objects.create(
            rule=self.rule, action_type="mark_read"
        )
        url = reverse("mails:rule_update", args=[self.rule.pk])
        cond = self.rule.conditions.first()
        response = self.client.post(url, {
            "rule-%d-name" % self.rule.pk: self.rule.name,
            "rule-%d-logic_expr" % self.rule.pk: "A",
            "rule-%d-apply_to_existing" % self.rule.pk: "",
            "rule-%d-symbol" % self.rule.pk: "star",
            "rule-%d-color" % self.rule.pk: "#c2a018",
            "rule-%d-color_dark" % self.rule.pk: "#e6c65a",
            "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
            "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
            "rule-%d-conditions-0-id" % self.rule.pk: cond.pk,
            "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
            "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
            "rule-%d-conditions-0-value" % self.rule.pk: "(?i)job",
            "rule-%d-conditions-0-negate" % self.rule.pk: "",
            **action_management("rule-%d-actions" % self.rule.pk),
            "rule-%d-actions-TOTAL_FORMS" % self.rule.pk: "1",
            "rule-%d-actions-INITIAL_FORMS" % self.rule.pk: "1",
            "rule-%d-actions-0-id" % self.rule.pk: action.pk,
            "rule-%d-actions-0-action_type" % self.rule.pk: "mark_read",
            "rule-%d-actions-0-callback_url" % self.rule.pk: "",
            "rule-%d-actions-0-DELETE" % self.rule.pk: "on",
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.rule.actions.count(), 0)

    def test_rule_save_keeps_action_row_and_fires_callback(self):
        from unittest import mock

        from mails.models import RuleAction

        action = RuleAction.objects.create(
            rule=self.rule, action_type="http_callback",
            callback_url="https://hooks.example.com/rule",
        )
        mail = create_mail(self.source, "<cbf@x>", subject="a job offer")
        url = reverse("mails:rule_update", args=[self.rule.pk])
        with mock.patch("urllib.request.urlopen") as ur:
            class R:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            ur.return_value = R()
            response = self.client.post(url, {
                "rule-%d-name" % self.rule.pk: self.rule.name,
                "rule-%d-logic_expr" % self.rule.pk: "A",
                "rule-%d-apply_to_existing" % self.rule.pk: "on",
                "rule-%d-symbol" % self.rule.pk: "star",
                "rule-%d-color" % self.rule.pk: "#c2a018",
                "rule-%d-color_dark" % self.rule.pk: "#e6c65a",
                "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
                "rule-%d-conditions-0-id" % self.rule.pk:
                    self.rule.conditions.first().pk,
                "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
                "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
                "rule-%d-conditions-0-value" % self.rule.pk: "(?i)job",
                "rule-%d-conditions-0-negate" % self.rule.pk: "",
                **action_management("rule-%d-actions" % self.rule.pk),
                "rule-%d-actions-TOTAL_FORMS" % self.rule.pk: "1",
                "rule-%d-actions-INITIAL_FORMS" % self.rule.pk: "1",
                "rule-%d-actions-0-id" % self.rule.pk: action.pk,
                "rule-%d-actions-0-action_type" % self.rule.pk: "http_callback",
                "rule-%d-actions-0-callback_url" % self.rule.pk:
                    "https://hooks.example.com/rule",
            })
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        # the action row survives the swap (rule_action_forms now in context)
        self.assertEqual(html.count("action-row"), 1)
        self.assertIn("https://hooks.example.com/rule", html)
        # the callback fired for the existing matching mail
        self.assertTrue(ur.called)
        subjects = [
            json.loads(call[0][0].data.decode("utf-8"))["object"]
            for call in ur.call_args_list
        ]
        self.assertIn("a job offer", subjects)

    def test_callback_refires_when_url_changes(self):
        from unittest import mock

        from mails.models import RuleAction, RuleActionLog

        action = RuleAction.objects.create(
            rule=self.rule, action_type="http_callback",
            callback_url="https://hooks.example.com/old",
        )
        mail = create_mail(self.source, "<re@x>", subject="a job offer")
        # first save with the option on fires and logs
        self.rule.apply_to_existing = True
        self.rule.save()
        with mock.patch("urllib.request.urlopen") as ur:
            class R:
                status = 200
                def __enter__(self):
                    return self
                def __exit__(self, *a):
                    return False
            ur.return_value = R()
            from mails.imap import reapply_rule
            reapply_rule(self.rule)
            first_calls = len(ur.call_args_list)
        self.assertGreaterEqual(first_calls, 1)
        # second reapply: no new calls (log guards)
        with mock.patch("urllib.request.urlopen") as ur2:
            ur2.return_value = R()
            reapply_rule(self.rule)
            self.assertEqual(len(ur2.call_args_list), 0)
        # now EDIT the callback URL via the form: log clears, re-fires
        url = reverse("mails:rule_update", args=[self.rule.pk])
        with mock.patch("urllib.request.urlopen") as ur3:
            ur3.return_value = R()
            response = self.client.post(url, {
                "rule-%d-name" % self.rule.pk: self.rule.name,
                "rule-%d-logic_expr" % self.rule.pk: "A",
                "rule-%d-apply_to_existing" % self.rule.pk: "on",
                "rule-%d-symbol" % self.rule.pk: "star",
                "rule-%d-color" % self.rule.pk: "#c2a018",
                "rule-%d-color_dark" % self.rule.pk: "#e6c65a",
                "rule-%d-conditions-TOTAL_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-INITIAL_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-MIN_NUM_FORMS" % self.rule.pk: "1",
                "rule-%d-conditions-MAX_NUM_FORMS" % self.rule.pk: "1000",
                "rule-%d-conditions-0-id" % self.rule.pk:
                    self.rule.conditions.first().pk,
                "rule-%d-conditions-0-target_field" % self.rule.pk: "subject",
                "rule-%d-conditions-0-match_type" % self.rule.pk: "regex",
                "rule-%d-conditions-0-value" % self.rule.pk: "(?i)job",
                "rule-%d-conditions-0-negate" % self.rule.pk: "",
                **action_management("rule-%d-actions" % self.rule.pk),
                "rule-%d-actions-TOTAL_FORMS" % self.rule.pk: "1",
                "rule-%d-actions-INITIAL_FORMS" % self.rule.pk: "1",
                "rule-%d-actions-0-id" % self.rule.pk: action.pk,
                "rule-%d-actions-0-action_type" % self.rule.pk: "http_callback",
                "rule-%d-actions-0-callback_url" % self.rule.pk:
                    "https://hooks.example.com/new",
            })
        self.assertEqual(response.status_code, 200)
        self.assertGreaterEqual(len(ur3.call_args_list), 1)
        action.refresh_from_db()
        self.assertEqual(action.callback_url, "https://hooks.example.com/new")

    def test_rule_count_endpoint(self):
        url = reverse("mails:rule_count", args=[self.rule.pk])
        create_mail(self.source, "<cnt1@x>", subject="a job offer")
        create_mail(self.source, "<cnt2@x>", subject="lunch plans")
        response = self.client.post(url, {"logic": "A"})
        data = response.json()
        self.assertTrue(data["valid"])
        # "<1@x>" from setUpTestData also matches (?i)job
        self.assertEqual(data["count"], 2)
        invalid = self.client.post(url, {"logic": "A &&"})
        self.assertFalse(invalid.json()["valid"])

    def test_rule_delete(self):
        url = reverse("mails:rule_delete", args=[self.rule.pk])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(CollectRule.objects.filter(pk=self.rule.pk).exists())


class ApplyRulesTests(TestCase):
    def test_apply_rules_creates_matches(self):
        source = create_source()
        rule1 = CollectRule.objects.create(name="r1")
        make_condition(rule1, "subject", "exact", "Hello")
        rule2 = CollectRule.objects.create(name="r2")
        make_condition(rule2, "body", "regex", "wor+d")
        rule3 = CollectRule.objects.create(name="r3")
        make_condition(rule3, "subject", "exact", "Nope")
        mail = create_mail(source, "<1@x>", subject="Hello", body="words")
        matched = apply_rules(mail)
        self.assertEqual(sorted(r.name for r in matched), ["r1", "r2"])
        self.assertEqual(RuleMatch.objects.filter(mail=mail).count(), 2)

    def test_apply_rules_skips_disabled(self):
        source = create_source()
        off = CollectRule.objects.create(name="off", enabled=False)
        make_condition(off, "subject", "exact", "Hello")
        mail = create_mail(source, "<1@x>", subject="Hello")
        self.assertEqual(apply_rules(mail), [])
        self.assertEqual(RuleMatch.objects.count(), 0)
