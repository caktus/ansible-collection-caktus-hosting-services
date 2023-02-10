# Ansible Collection - caktus.hosting_services

A collection of useful Ansible roles for managing virtual and physical servers

We aim to support the following operating systems:

- Ubuntu 20.04
- Ubuntu 22.04

## `hosting_services.email_forwarding`

Forwards some or all mail via an external SMTP service such as SES, via the `Oefenweb.ansible-postfix` role.

```yaml
# playbook.yaml
- hosts: all
  become: yes
  tags: email
  roles:
    - caktus.hosting_services.email_forwarding
```

```yaml
# vars file
email_forwarding_smtp_host: ...
email_forwarding_smtp_user: AKI...
email_forwarding_smtp_password: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  ...

# Optionally send all mail for root to the configured address
email_forwarding_root_destination: "user@example.com"

# Optionally override the sender for all outgoing mail (not suitable if your
# app already sets an acceptable and more desirable From address):
email_forwarding_rewrite_sender: "yoursite+{{ inventory_hostname | replace('_', '-') }}@example.com"
```

Include required role in `requirements.yaml`:

```yaml
# requirements.yaml
roles:
  - name: oefenweb.postfix
    src: https://github.com/Oefenweb/ansible-postfix
```

## `hosting_services.rsyslog_forwarding`

Forwards logs to an external syslog server via rsyslog.

```yaml
# playbook.yaml
- hosts: all
  become: yes
  tags: rsyslog
  roles:
    - caktus.hosting_services.rsyslog_forwarding
```

```yaml
# vars file
rsyslog_forwarding_endpoint: logsN.papertrailapp.com:NNNNN
```

## `hosting_services.smartd`

Installs and runs smartd tests periodically on all attached devices that support it.

```yaml
# playbook.yaml
- hosts: bare_metal
  become: yes
  tags: smartd
  roles:
    - caktus.hosting_services.smartd
```

```yaml
# vars file

# Define an admin email to receive notices from smartd:
smartd_admin_email: user@example.com

# Optionally override the smartd scan schedule. The default is to start a short self-test
# every day between 3-4am, and a long self test Saturdays between 4-5am.
smartd_scan_schedule: "(S/../.././03|L/../../6/04)"
```

## `hosting_services.statuscake_monitoring`

Add docs here.

## `hosting_services.users`

Enables passwordless sudo for all managed users and includes the `weareinteractive.users` role to do the heavy lifting.

```yaml
# playbook.yaml
- hosts: all
  become: yes
  tags: users
  roles:
    - caktus.hosting_services.users
```

```yaml
# vars file
# Remove default user. You might need to run your playbook initially with
# "-u ubuntu -e users_remove=[]" until the final users are provisioned.
users_remove:
  - ubuntu

# Users to provision on servers.
# Find your ssh key with: `cat ~/.ssh/id_*.pub` (should be one line)
# Optionally generate password via `mkpasswd -m sha-512 -R 2000000`
users:
  # in alphabetical order
  - username: ...
    password: $6$rounds=2000000$....
    authorized_keys:
      - ssh-ed25519 ...
# You can optionally override the default groups and shell or disable
# passwordless sudo, if needed:
# users_groups: [adm, dialout, docker, sudo]
# users_shell: /bin/bash
# users_enable_passwordless_sudo: no
```

Include required role in `requirements.yaml`:

```yaml
# requirements.yaml
roles:
  - src: weareinteractive.users
```
