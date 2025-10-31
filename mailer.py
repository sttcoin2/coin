"""Command-line tool for sending marketing emails with unsubscribe tracking."""
from __future__ import annotations

import argparse
import csv
import json
import os
import smtplib
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set

DEFAULT_UNSUBSCRIBED_PATH = Path("data/unsubscribed.json")


class MailerError(Exception):
    """Base exception for predictable mailer errors."""


@dataclass
class SmtpSettings:
    host: str
    port: int
    username: str | None
    password: str | None
    use_tls: bool
    use_ssl: bool

    @classmethod
    def from_env(cls) -> "SmtpSettings":
        """Create settings from environment variables."""
        host = os.getenv("SMTP_HOST")
        if not host:
            raise MailerError("SMTP_HOST environment variable is required")

        port_value = os.getenv("SMTP_PORT", "587")
        try:
            port = int(port_value)
        except ValueError as exc:
            raise MailerError(f"Invalid SMTP_PORT value: {port_value!r}") from exc

        username = os.getenv("SMTP_USERNAME") or None
        password = os.getenv("SMTP_PASSWORD") or None
        use_tls = _str_to_bool(os.getenv("SMTP_USE_TLS", "true"))
        use_ssl = _str_to_bool(os.getenv("SMTP_USE_SSL", "false"))

        return cls(host=host, port=port, username=username, password=password, use_tls=use_tls, use_ssl=use_ssl)


@dataclass
class Recipient:
    email: str
    row: Dict[str, str]

    @property
    def normalized_email(self) -> str:
        return normalise_email(self.email)


def _str_to_bool(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in {"1", "true", "yes", "on"}


def normalise_email(email: str) -> str:
    return email.strip().lower()


def load_unsubscribed(path: Path | None = None) -> Set[str]:
    if path is None:
        path = DEFAULT_UNSUBSCRIBED_PATH
    if not path.exists():
        return set()
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except json.JSONDecodeError as exc:
        raise MailerError(f"Could not parse unsubscribe ledger {path}: {exc}") from exc

    if not isinstance(data, list):
        raise MailerError(f"Unexpected data format in unsubscribe ledger {path}: expected a list of emails")

    return {normalise_email(email) for email in data}


def save_unsubscribed(emails: Iterable[str], path: Path | None = None) -> None:
    if path is None:
        path = DEFAULT_UNSUBSCRIBED_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    sorted_emails = sorted({normalise_email(email) for email in emails if email})
    with path.open("w", encoding="utf-8") as fh:
        json.dump(sorted_emails, fh, indent=2)
        fh.write("\n")


def read_recipients(csv_path: Path) -> List[Recipient]:
    if not csv_path.exists():
        raise MailerError(f"Recipients file not found: {csv_path}")

    with csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing_columns = {"email"} - set(reader.fieldnames or [])
        if missing_columns:
            raise MailerError(f"Recipients file must include columns: {', '.join(sorted(missing_columns))}")

        recipients: List[Recipient] = []
        for row in reader:
            email = (row.get("email") or "").strip()
            if not email:
                continue
            recipients.append(Recipient(email=email, row={k: (v or "").strip() for k, v in row.items()}))

    return recipients


def render_template(template_text: str, context: Dict[str, str]) -> str:
    try:
        return template_text.format(**context)
    except KeyError as exc:
        missing_key = exc.args[0]
        raise MailerError(
            f"Missing placeholder '{missing_key}' for template rendering. Check the CSV columns or template content."
        ) from exc


def build_message(subject: str, sender: str, recipient: Recipient, body: str) -> EmailMessage:
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = sender
    message["To"] = recipient.email
    message.set_content(body)
    return message


def send_messages(
    messages: Sequence[EmailMessage], settings: SmtpSettings | None, dry_run: bool = False
) -> None:
    if dry_run:
        for msg in messages:
            print("=" * 60)
            print(f"To: {msg['To']}")
            print(f"Subject: {msg['Subject']}")
            print()
            print(msg.get_content())
        print("=" * 60)
        print(f"Total messages prepared: {len(messages)} (dry run, nothing sent)")
        return

    if not messages:
        print("No messages to send.")
        return

    if settings is None:
        raise MailerError("SMTP settings are required when not running in dry-run mode")

    if settings.use_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings.host, settings.port)
    else:
        smtp = smtplib.SMTP(settings.host, settings.port)

    try:
        if not settings.use_ssl and settings.use_tls:
            smtp.starttls()
        if settings.username:
            smtp.login(settings.username, settings.password or "")

        for msg in messages:
            smtp.send_message(msg)
            print(f"Sent email to {msg['To']}")
    finally:
        smtp.quit()


def handle_send(args: argparse.Namespace) -> None:
    csv_path = Path(args.clients)
    template_path = Path(args.template)

    recipients = read_recipients(csv_path)
    unsubscribed = load_unsubscribed()

    if not recipients:
        print("Recipient list is empty. Nothing to send.")
        return

    template_text = template_path.read_text(encoding="utf-8")

    active_recipients = [r for r in recipients if r.normalized_email not in unsubscribed]
    skipped_recipients = [r for r in recipients if r.normalized_email in unsubscribed]

    messages: List[EmailMessage] = []
    for recipient in active_recipients:
        context = {**recipient.row}
        context.setdefault("email", recipient.email)
        body = render_template(template_text, context)
        message = build_message(args.subject, args.from_address, recipient, body)
        messages.append(message)

    if skipped_recipients:
        print(
            f"Skipping {len(skipped_recipients)} unsubscribed recipient(s): "
            + ", ".join(r.email for r in skipped_recipients)
        )

    if not messages:
        print("No eligible recipients after applying unsubscribe list.")
        return

    if args.dry_run:
        send_messages(messages, settings=None, dry_run=True)
        return

    settings = SmtpSettings.from_env()
    send_messages(messages, settings, dry_run=False)


def handle_unsubscribe(args: argparse.Namespace) -> None:
    email = normalise_email(args.email)
    if not email:
        raise MailerError("Email is required for unsubscribe command")

    unsubscribed = load_unsubscribed()
    if email in unsubscribed:
        print(f"{args.email} is already unsubscribed.")
        return

    unsubscribed.add(email)
    save_unsubscribed(unsubscribed)
    print(f"Added {args.email} to the unsubscribe list.")


def handle_resubscribe(args: argparse.Namespace) -> None:
    email = normalise_email(args.email)
    unsubscribed = load_unsubscribed()

    if email not in unsubscribed:
        print(f"{args.email} is not in the unsubscribe list.")
        return

    unsubscribed.remove(email)
    save_unsubscribed(unsubscribed)
    print(f"Removed {args.email} from the unsubscribe list.")


def handle_list_unsubscribed(_: argparse.Namespace) -> None:
    unsubscribed = sorted(load_unsubscribed())
    if not unsubscribed:
        print("No unsubscribed contacts found.")
        return

    print("Unsubscribed contacts:")
    for email in unsubscribed:
        print(f" - {email}")


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ledger",
        default=str(DEFAULT_UNSUBSCRIBED_PATH),
        help="Path to the JSON file that stores unsubscribe records (default: data/unsubscribed.json)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    send_parser = subparsers.add_parser("send", help="Send marketing emails to recipients in a CSV file")
    send_parser.add_argument("--clients", required=True, help="Path to the CSV file containing recipients")
    send_parser.add_argument("--template", required=True, help="Path to the text template to render")
    send_parser.add_argument("--subject", required=True, help="Email subject line")
    send_parser.add_argument("--from-address", required=True, help="Sender email address")
    send_parser.add_argument("--dry-run", action="store_true", help="Preview emails without sending them")
    send_parser.set_defaults(func=handle_send)

    unsubscribe_parser = subparsers.add_parser("unsubscribe", help="Add an email address to the unsubscribe list")
    unsubscribe_parser.add_argument("email", help="Email address to unsubscribe")
    unsubscribe_parser.set_defaults(func=handle_unsubscribe)

    resubscribe_parser = subparsers.add_parser("resubscribe", help="Remove an email address from the unsubscribe list")
    resubscribe_parser.add_argument("email", help="Email address to resubscribe")
    resubscribe_parser.set_defaults(func=handle_resubscribe)

    list_parser = subparsers.add_parser("list-unsubscribed", help="List all unsubscribed email addresses")
    list_parser.set_defaults(func=handle_list_unsubscribed)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = create_parser()
    args = parser.parse_args(argv)

    ledger_path = Path(args.ledger)
    global DEFAULT_UNSUBSCRIBED_PATH
    DEFAULT_UNSUBSCRIBED_PATH = ledger_path

    try:
        args.func(args)
    except MailerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
