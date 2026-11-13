"""בדיקות ערוצי התראה: Telegram + מייל, כשל של ערוץ אחד, שליחה חוזרת בלי כפילות. אין שליחה אמיתית."""
import smtplib

import pytest

from app.notifier import EmailSender, Notifier, format_message


class Chan:
    def __init__(self, name, fail=False, configured=True):
        self.name, self.fail, self.configured, self.sent = name, fail, configured, []

    async def send(self, text):
        if self.fail:
            raise RuntimeError("תקלה מדומה")
        self.sent.append(text)


@pytest.mark.asyncio
async def test_sends_to_all_channels(db):
    tg, mail = Chan("Telegram"), Chan("מייל")
    n = await Notifier(senders=[tg, mail]).notify(db, "test", "k-all", "שלום")
    assert n.sent and n.channels_sent == ["Telegram", "מייל"]
    assert tg.sent == ["שלום"] and mail.sent == ["שלום"]


@pytest.mark.asyncio
async def test_one_channel_fails_retry_only_that_channel(db):
    tg, mail = Chan("Telegram"), Chan("מייל", fail=True)
    notifier = Notifier(senders=[tg, mail])
    n = await notifier.notify(db, "test", "k-partial", "שלום")
    assert n.sent is False and n.channels_sent == ["Telegram"] and "מייל" in n.error
    mail.fail = False
    await notifier.retry_unsent(db)
    assert n.sent is True
    assert tg.sent == ["שלום"]          # טלגרם לא קיבל כפילות
    assert mail.sent == ["שלום"]


@pytest.mark.asyncio
async def test_unconfigured_channel_is_skipped(db):
    tg, mail = Chan("Telegram"), Chan("מייל", configured=False)
    n = await Notifier(senders=[tg, mail]).notify(db, "test", "k-skip", "שלום")
    assert n.sent and n.channels_sent == ["Telegram"]


@pytest.mark.asyncio
async def test_no_channels_configured(db):
    n = await Notifier(senders=[Chan("Telegram", configured=False)]).notify(db, "test", "k-none", "שלום")
    assert n.sent is False and "לא הוגדר" in n.error


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=None):
        self.host, self.port, self.messages, self.tls, self.login_user = host, port, [], False, None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        self.tls = True

    def login(self, user, pw):
        self.login_user = user

    def send_message(self, msg):
        self.messages.append(msg)


@pytest.mark.asyncio
async def test_email_sender_builds_hebrew_message(monkeypatch, db):
    FakeSMTP.instances.clear()
    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    es = EmailSender("smtp.example.invalid", 587, "me@example.invalid", "app-pass", "", "a@example.invalid, b@example.invalid")
    text = format_message("on_sale", None, details="[דמה] בדיקה")
    await es.send(text)
    smtp = FakeSMTP.instances[0]
    assert smtp.tls and smtp.login_user == "me@example.invalid"
    msg = smtp.messages[0]
    assert "נפתחה מכירה" in msg["Subject"]
    assert msg["To"] == "a@example.invalid, b@example.invalid"
    assert "[דמה] בדיקה" in msg.get_content()


@pytest.mark.asyncio
async def test_email_error_hides_details(monkeypatch):
    class Boom(FakeSMTP):
        def login(self, user, pw):
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials for me@example.invalid app-pass")
    monkeypatch.setattr(smtplib, "SMTP", Boom)
    es = EmailSender("smtp.example.invalid", 587, "me@example.invalid", "app-pass", "", "a@example.invalid")
    with pytest.raises(RuntimeError) as ei:
        await es.send("x")
    assert "app-pass" not in str(ei.value) and "SMTPAuthenticationError" in str(ei.value)


def test_email_not_configured_without_password():
    assert EmailSender("smtp.gmail.com", 587, "u@example.invalid", "", "", "a@example.invalid").configured is False
