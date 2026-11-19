# Security policy

## Supported versions

Security fixes go into the latest release. Upgrade to it to get them.

## Reporting a vulnerability

Please **do not** open a public issue. Use
[GitHub's private vulnerability reporting](https://github.com/lobojoel2003/Pipetrace/security/advisories/new)
and include steps to reproduce. You'll get an answer within a week.

## What Pipetrace stores

- The service line inventory, which water systems are required to make public.
- Inspection requests and pipe photos from residents: names, phone numbers, email
  addresses and pictures. These are visible only to staff accounts. Photos are
  re-encoded on upload, which removes location (GPS) and other metadata, and they
  are never served from a public URL.

Deployments should run behind HTTPS with `PIPETRACE_SECURE=1`, which turns on
secure cookies, HSTS and HTTPS redirects.
