# Simple Marketing Mailer

This repository contains a small Python command-line tool that helps you send plain text marketing emails while respecting unsubscribe requests.

## Features

- Read a list of recipients from a CSV file.
- Personalise a text template with placeholders such as `{name}` or `{company}`.
- Send emails through any SMTP provider using credentials stored in environment variables.
- Keep track of unsubscribe requests locally so you do not contact those addresses again.
- Dry-run mode so you can preview personalised emails before sending them.

## Project structure

```
.
├── data/                  # Stores the unsubscribe ledger (created automatically)
├── mailer.py              # CLI application for sending emails and managing unsubscribes
├── templates/             # Example text templates
└── README.md              # This documentation
```

## Prerequisites

- Python 3.9 or newer.
- Access to an SMTP server (for example: Gmail, SendGrid, Mailgun, etc.).

## Environment variables

Set the following environment variables before sending emails:

| Variable | Description | Example |
|----------|-------------|---------|
| `SMTP_HOST` | SMTP server hostname | `smtp.sendgrid.net` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USERNAME` | Username for SMTP authentication | `apikey` |
| `SMTP_PASSWORD` | Password or API key | `SG.xxxxx` |
| `SMTP_USE_TLS` | Enable STARTTLS upgrade (default: `true`) | `false` |
| `SMTP_USE_SSL` | Use implicit TLS instead of STARTTLS (default: `false`) | `true` |

> `SMTP_USE_SSL` takes precedence over `SMTP_USE_TLS`. Leave both unset to use plain SMTP (not recommended).

## Recipient list CSV

Create a CSV file with at least the following headers:

```csv
email,name,company,call_to_action_url,unsubscribe_url,sender_name,sender_title
person@example.com,Alex,Example Co,https://cal.example.com/alex,https://example.com/unsubscribe?email=person@example.com,"Jamie from Example","Customer Success Manager"
```

Any additional columns become available as template placeholders.

## Usage

Install dependencies (there are none beyond the Python standard library) and run the CLI:

```bash
python mailer.py --help
```

### Send emails

```bash
python mailer.py send \
  --clients clients.csv \
  --template templates/marketing_email.txt \
  --subject "Let's schedule your free strategy session" \
  --from-address marketing@example.com
```

Add `--dry-run` to print emails instead of sending them. Only addresses that have **not** unsubscribed will receive the message.

### Manage unsubscribe requests

Record an unsubscribe event manually (for example after a user submits a form):

```bash
python mailer.py unsubscribe user@example.com
```

List all unsubscribed addresses:

```bash
python mailer.py list-unsubscribed
```

To allow a contact back onto your list, run:

```bash
python mailer.py resubscribe user@example.com
```

## Notes on compliance

- Always include a clear unsubscribe link in every email. The template in `templates/marketing_email.txt` contains a `{unsubscribe_url}` placeholder for this purpose.
- If you manage a large list or need automated unsubscribe landing pages, consider integrating this script with a database or dedicated email service provider.
- Make sure you comply with all applicable anti-spam regulations (CAN-SPAM, GDPR, etc.) when contacting your clients.

## Development

The codebase uses only standard library modules, so there is no `requirements.txt`. Run the linter / formatter of your choice or simply execute the script in dry-run mode during development.
