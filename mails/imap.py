"""IMAP fetching utilities.

Strict constraint: the collector never alters mail state on the IMAP server.
BODY.PEEK is used everywhere, messages are never marked as seen, moved or
deleted.
"""

import email
import email.header
import imaplib
import logging
import re
from email.utils import parsedate_to_datetime

from django.utils import timezone

from .models import (
    CollectRule,
    MailMessage,
    MailSource,
    RuleMatch,
    run_action_once,
)

logger = logging.getLogger(__name__)

LINK_RE = re.compile(r"https?://[^\s<>\"]+")


def extract_body(msg):
    """Return the plain-text body, falling back to html converted to text."""
    body_part = None
    html_part = None
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_maintype() == "multipart":
                continue
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", "")).lower()
            if disp == "attachment":
                continue
            if ctype == "text/plain" and body_part is None:
                body_part = part
            elif ctype == "text/html" and html_part is None:
                html_part = part
    else:
        if msg.get_content_type() == "text/html":
            html_part = msg
        else:
            body_part = msg

    if body_part is not None:
        charset = body_part.get_content_charset() or "utf-8"
        try:
            text = body_part.get_payload(decode=True).decode(charset, errors="replace")
        except (LookupError, AttributeError):
            text = ""
        if text.strip():
            return text

    if html_part is not None:
        from django.utils.html import strip_tags

        charset = html_part.get_content_charset() or "utf-8"
        try:
            html = html_part.get_payload(decode=True).decode(charset, errors="replace")
        except (LookupError, AttributeError):
            return ""
        return strip_tags(html).strip()

    return ""


def extract_link(body):
    match = LINK_RE.search(body or "")
    if match:
        return match.group(0).rstrip('.,;:)\'"')
    return ""


def decode_header_value(raw):
    """Decode an RFC 2047 MIME-encoded header (e.g.
    =?UTF-8?B?...?=) into a plain unicode string. Folded (multi-line)
    headers are unfolded first."""
    if not raw:
        return ""
    raw = raw.replace("\r\n ", " ").replace("\n ", " ")
    try:
        parts = email.header.decode_header(raw)
        decoded = []
        for text, charset in parts:
            if isinstance(text, bytes):
                decoded.append(text.decode(charset or "utf-8", errors="replace"))
            else:
                decoded.append(text)
        return "".join(decoded)
    except Exception:
        return raw


def extract_date(msg):
    raw = msg.get("Date")
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return None


def reapply_rule(rule):
    """Retroactively apply one rule to all already-stored mails.

    Used when a rule is created or changed so that it also matches
    previously collected mails: matches are added for newly matching
    mails and removed for mails that no longer match the rule.
    Returns the number of stored matches after the re-application.
    """
    from .models import run_action_once

    logger.info(
        "reapply_rule id=%s name=%r enabled=%s apply_to_existing=%s "
        "conditions=%s actions=%s mails=%s",
        rule.pk, rule.name, rule.enabled, rule.apply_to_existing,
        rule.conditions.count(), rule.actions.count(),
        MailMessage.objects.count(),
    )
    kept = 0
    actions_fired = 0
    for mail in MailMessage.objects.iterator():
        should_match = rule.matches_mail(mail)
        existing = RuleMatch.objects.filter(rule=rule, mail=mail).first()
        if should_match:
            if not existing:
                RuleMatch.objects.create(rule=rule, mail=mail)
            kept += 1
            if rule.apply_to_existing:
                for action in rule.actions.all():
                    try:
                        ran = run_action_once(action, mail)
                        if ran:
                            actions_fired += 1
                            logger.info(
                                "action fired: rule=%r action=%s pk=%s "
                                "url=%r mail=%s",
                                rule.name, action.action_type, action.pk,
                                action.callback_url, mail.message_id,
                            )
                    except Exception:
                        logger.exception(
                            "Action %s (pk=%s) failed on mail %s",
                            action.action_type, action.pk, mail.message_id,
                        )
        elif existing:
            existing.delete()
    logger.info(
        "reapply_rule done: rule=%r matched=%s actions_fired=%s",
        rule.name, kept, actions_fired,
    )
    return kept


def apply_rules(mail):
    """Apply every enabled rule to a stored mail, create RuleMatch rows
    and run the rules' actions."""
    matched = []
    for rule in CollectRule.objects.filter(enabled=True).prefetch_related("actions"):
        if rule.matches_mail(mail):
            RuleMatch.objects.get_or_create(rule=rule, mail=mail)
            for action in rule.actions.all():
                try:
                    run_action_once(action, mail)
                except Exception:
                    logger.exception("Action %s failed", action)
            matched.append(rule)
    return matched


def fetch_source(source, connection_factory=None):
    """Fetch new messages from one source.

    ``connection_factory`` is injectable for tests; production code uses
    ``imaplib`` directly. Returns the number of new mails stored.
    """
    connection_factory = connection_factory or _default_connection_factory
    conn = connection_factory(source)
    try:
        status, _data = conn.login(source.username, source.password)
        if status != "OK":
            raise ConnectionError(
                "Login failed for %s (status %s)" % (source.username, status)
            )
        status, data = conn.select(source.folder, readonly=True)
        if status != "OK":
            raise ConnectionError(
                "Cannot select mailbox %s (status %s)" % (source.folder, status)
            )
        status, data = conn.search(None, "ALL")
        if status != "OK":
            raise ConnectionError("Cannot search mailbox (status %s)" % status)
        uids = (data[0] or b"").split()
        new_count = 0
        for uid in uids:
            status, data = conn.fetch(uid, "(BODY.PEEK[])")
            if status != "OK" or not data or data[0] is None:
                logger.warning("Fetch failed for UID %s on %s", uid, source.name)
                continue
            raw = data[0][1]
            new_count += _store_message(source, raw)
        return new_count
    finally:
        try:
            conn.logout()
        except Exception:
            logger.exception("Error while logging out from %s", source.name)


def _default_connection_factory(source):
    if source.use_ssl:
        return imaplib.IMAP4_SSL(source.host, source.port)
    return imaplib.IMAP4(source.host, source.port)


def _store_message(source, raw):
    try:
        msg = email.message_from_bytes(raw)
    except Exception:
        logger.exception("Cannot parse message on %s", source.name)
        return 0
    message_id = (msg.get("Message-ID") or "").strip()
    if not message_id:
        message_id = "no-message-id-%d" % hash(raw)
    existing = MailMessage.objects.filter(source=source, message_id=message_id).exists()
    if existing:
        return 0
    body = extract_body(msg)
    date = extract_date(msg)
    sender_raw = (msg.get("From") or "")[:998]
    subject_raw = (msg.get("Subject") or "")[:998]
    mail = MailMessage.objects.create(
        source=source,
        message_id=message_id,
        sender=decode_header_value(sender_raw)[:998],
        sender_raw=sender_raw,
        subject=decode_header_value(subject_raw)[:998],
        subject_raw=subject_raw,
        date=date,
        body=body,
        link=extract_link(body)[:2048],
    )
    apply_rules(mail)
    return 1


def run_fetch(source_qs=None, connection_factory=None):
    """Fetch every enabled source whose interval has elapsed."""
    sources = (source_qs if source_qs is not None else MailSource.objects.all()).filter(
        enabled=True
    )
    results = {}
    for source in sources:
        if not source.interval_elapsed:
            continue
        try:
            count = fetch_source(source, connection_factory=connection_factory)
        except Exception as exc:
            logger.exception("Fetch failed for source %s", source.name)
            results[source.name] = {"error": str(exc), "new": 0}
            continue
        source.last_fetch_at = timezone.now()
        source.save(update_fields=["last_fetch_at"])
        results[source.name] = {"new": count}
    return results
