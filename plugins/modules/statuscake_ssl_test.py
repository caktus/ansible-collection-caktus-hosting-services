from ansible.module_utils.basic import AnsibleModule
from ansible_collections.caktus.hosting_services.plugins.module_utils.statuscake import (
    SSLTest,
)


def main():
    argument_spec = {
        "api_key": {"required": True, "type": "str", "no_log": True},
        "state": {"required": True, "type": "str", "choices": ["present", "absent"]},
        "website_url": {"required": True, "type": "str"},
        "check_rate": {
            "required": True,
            "type": "int",
            "choices": [300, 600, 1800, 86400, 2073600],
        },
        "contact_groups": {"required": False, "type": "list"},
        "alert_at": {"required": True, "type": "bool"},
        "alert_reminder": {"required": True, "type": "bool"},
        "alert_expiry": {"required": True, "type": "bool"},
        "alert_broken": {"required": True, "type": "bool"},
        "alert_mixed": {"required": True, "type": "bool"},
        "follow_redirects": {"required": False, "type": "bool"},
        "paused": {"required": False, "type": "bool"},
        "hostname": {"required": False, "type": "str"},
        "user_agent": {"required": False, "type": "str"},
        "log_file": {"required": False, "type": "str"},
    }
    module = AnsibleModule(argument_spec=argument_spec, supports_check_mode=False)
    api_key = module.params["api_key"]
    website_url = module.params["website_url"]
    state = module.params["state"]
    test = SSLTest(
        api_key=api_key,
        state=state,
        website_url=website_url,
        check_rate=module.params["check_rate"],
        contact_groups=module.params["contact_groups"],
        alert_at=module.params["alert_at"],
        alert_reminder=module.params["alert_reminder"],
        alert_expiry=module.params["alert_expiry"],
        alert_broken=module.params["alert_broken"],
        alert_mixed=module.params["alert_mixed"],
        follow_redirects=module.params["follow_redirects"],
        paused=module.params["paused"],
        hostname=module.params["hostname"],
        user_agent=module.params["user_agent"],
        log_file=module.params["log_file"],
    )
    status = test.sync()
    if status.success:
        module.exit_json(
            changed=status.changed,
            msg=status.message,
        )
    else:
        module.fail_json(msg=status.message)


if __name__ == "__main__":
    main()
