# Changelog

## v0.8.0 - 2026-08-12

- Add `regions` to `UptimeTest` LIST_PARAMETERS
- Migrate project tooling to uv
- Switch pre-commit hooks to ruff and uv-lock

## v0.7.2 - 2025-01-31

- Fix `needs_reboot` path check (#48)

## v0.7.1 - 2025-01-09

- Retry `os_updates` tasks prone to failure (#46)

## v0.7.0 - 2025-01-09

- Add support for `os_updates_reboot_timeout` (#45)

## v0.6.1 - 2024-03-01

- Remove `get_md5` check from reboot task (#44)

## v0.6.0 - 2023-02-15

- Add `os_updates` role (#43)

## v0.5.0 - 2023-02-10

- Add `email_forwarding`, `rsyslog_forwarding`, `smartd`, and `users` roles (#41)

## v0.4.0 - 2022-12-09

- Update StatusCake list parameter encoding (#42)

## v0.3.1 - 2022-05-03

- Increase StatusCake API page limit to 100 (#38)

## v0.3.0 - 2022-02-07

- Add `statuscake_ssl_test` module and `SSLTest` class (#33, #35)

## v0.2.0 - 2022-01-18

- Add pre-commit hooks (#20)
- Add remaining module parameters to role (#29)
- Convert CSV arguments to lists rather than strings (#27, #23)
- Clean up merged uptime tests (#28)
- Handle immutable fields (#19)
- Fix user & password parameters (#30)

## v0.1.0 - 2022-01-12

- Initial `statuscake_uptime_test` script: create, list, and delete tests (#8, #9)
- Log file configuration (#12)
- User-change detection (#16)
- Status updates (#18)
- Restructure project as an Ansible collection (#11)
- Apply Black code formatting (#10)
