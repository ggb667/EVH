# EVH Daily Summary Lambda + EventBridge Setup

This document records the current production setup for the EVH daily Gmail summary job.

## Purpose

Run the EVH daily email summary from AWS Lambda on a schedule via EventBridge, using Gmail OAuth credentials stored in AWS Secrets Manager.

## Components

### Lambda function

- **Function name:** `Process_Emails_for_EVH`
- **Region:** `us-east-1`
- **Runtime:** Python
- **Trigger:** EventBridge
- **Test payload:** `{ "dry_run": false }`

### Secret

- **Name:** `evh/gmail/evhstaff@gmail.com/daily-summary/oauth`
- **ARN:** `arn:aws:secretsmanager:us-east-1:274530612068:secret:evh/gmail/evhstaff@gmail.com/daily-summary/oauth-2yczPR`

Secret JSON shape:

```json
{
  "client_id": "...",
  "client_secret": "...",
  "refresh_token": "..."
}
```

### Lambda execution role

- **Role name:** `Process_Emails_for_EVH-role-928a3om8`

Inline policy attached:

- `logs:CreateLogGroup`
- `logs:CreateLogStream`
- `logs:PutLogEvents`
- `secretsmanager:GetSecretValue` on the Gmail OAuth secret ARN above

### EventBridge / Scheduler

EventBridge is already configured to invoke the Lambda.

Recommended payload:

```json
{
  "dry_run": false
}
```

## Runtime behavior

The handler:

1. reads Gmail OAuth credentials from Secrets Manager
2. refreshes the Gmail token
3. verifies the mailbox is `evhstaff@gmail.com`
4. loads unread mail from the last day
5. builds the summary
6. writes artifacts to:
   - `/tmp/evh_daily_email_summary.md`
   - `/tmp/evh_daily_email_summary.json`
7. sends the summary email to:
   - `evhstaff+daily_summary@gmail.com`

## Validation

- `dry_run: true` was used earlier for placeholder validation
- `dry_run: false` passed successfully on the real path

## Notes

- No extra guardrails were requested.
- No VPC, Function URL, or tenant isolation is required for this setup.
- If RDS/Aurora resources are not visible in the console, confirm the AWS Region and account first.
