import pytest
from ansible_collections.caktus.hosting_services.plugins.modules.cloudformation_validate import (
    ValidationError,
    validate,
)


def test_returns_validation_metadata(cloudformation):
    client, stubber = cloudformation
    template_body = '{"Resources": {}}'
    stubber.add_response(
        "validate_template",
        {
            "Capabilities": ["CAPABILITY_IAM"],
            "CapabilitiesReason": "The template contains IAM resources.",
            "DeclaredTransforms": [],
            "Description": "Example template",
            "Parameters": [
                {
                    "ParameterKey": "AccountId",
                    "DefaultValue": "111122223333",
                    "NoEcho": False,
                }
            ],
        },
        {"TemplateBody": template_body},
    )

    result = validate(client, template_body)

    assert result == {
        "capabilities": ["CAPABILITY_IAM"],
        "capabilities_reason": "The template contains IAM resources.",
        "declared_transforms": [],
        "description": "Example template",
        "parameters": [
            {
                "ParameterKey": "AccountId",
                "DefaultValue": "111122223333",
                "NoEcho": False,
            }
        ],
    }


def test_names_validation_failure(cloudformation):
    client, stubber = cloudformation
    template_body = "invalid"
    stubber.add_client_error(
        "validate_template",
        service_error_code="ValidationError",
        service_message="Template format error",
        expected_params={"TemplateBody": template_body},
    )

    with pytest.raises(
        ValidationError,
        match="Template format error",
    ):
        validate(client, template_body)
