/**
 * API reference data, generated from the OpenAPI schema.
 *
 * Do not edit by hand: run `make api-reference` (or
 * `python scripts/generate_api_reference.py`) after changing a router. A
 * hand-maintained list of 78 operations is a list that goes stale.
 */

export type ApiParameter = {
  name: string;
  location: string;
  required: boolean;
  type: string;
  description: string;
};

export type ApiResponse = { status: string; description: string; type: string };

export type ApiOperation = {
  id: string;
  method: string;
  path: string;
  tag: string;
  summary: string;
  description: string;
  deprecated: boolean;
  parameters: ApiParameter[];
  body: { type: string; required: boolean } | null;
  responses: ApiResponse[];
};

export type ApiGroup = { tag: string; title: string; blurb: string };

export const API_TITLE = "SerpFlow";
export const API_VERSION = "0.1.0";
export const API_OPERATION_COUNT = 78;
export const API_PATH_COUNT = 69;

export const API_GROUPS: ApiGroup[] = [
  {
    "tag": "search",
    "title": "Search and planning",
    "blurb": "Plan without spending, execute, and stream a run as it happens."
  },
  {
    "tag": "runs",
    "title": "Runs",
    "blurb": "Run history, the Run Inspector payload, replay and false-hit reports."
  },
  {
    "tag": "catalog",
    "title": "Catalog",
    "blurb": "Engines, capability tags, the typed graph, and the paths that reach an engine."
  },
  {
    "tag": "governance",
    "title": "Governance",
    "blurb": "Budgets, cache administration, analytics, benchmarks, the audit log and alerts."
  },
  {
    "tag": "auth",
    "title": "Authentication",
    "blurb": "Registration, sessions, email verification and password reset."
  },
  {
    "tag": "organizations",
    "title": "Organizations",
    "blurb": "Projects, members, API keys and organization settings."
  },
  {
    "tag": "credentials",
    "title": "Upstream credentials",
    "blurb": "The encrypted SerpApi credential vault: attach, validate, rotate, revoke."
  },
  {
    "tag": "infrastructure",
    "title": "Infrastructure",
    "blurb": "Liveness, readiness and Prometheus metrics."
  }
];

export const API_OPERATIONS: ApiOperation[] = [
  {
    "id": "register_v1_auth_register_post",
    "method": "POST",
    "path": "/v1/auth/register",
    "tag": "auth",
    "summary": "Register",
    "description": "Create a user, their organization, a first project and a default budget.",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "RegisterRequest",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "TokenResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "login_v1_auth_login_post",
    "method": "POST",
    "path": "/v1/auth/login",
    "tag": "auth",
    "summary": "Login",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "LoginRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "TokenResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "refresh_v1_auth_refresh_post",
    "method": "POST",
    "path": "/v1/auth/refresh",
    "tag": "auth",
    "summary": "Refresh",
    "description": "Refresh rotation: reusing a rotated token is rejected.",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "RefreshRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "TokenResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "logout_v1_auth_logout_post",
    "method": "POST",
    "path": "/v1/auth/logout",
    "tag": "auth",
    "summary": "Logout",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "session_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "me_v1_auth_me_get",
    "method": "GET",
    "path": "/v1/auth/me",
    "tag": "auth",
    "summary": "Me",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "MeResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_sessions_v1_auth_sessions_get",
    "method": "GET",
    "path": "/v1/auth/sessions",
    "tag": "auth",
    "summary": "List Sessions",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "SessionResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "revoke_session_v1_auth_sessions__session_id__delete",
    "method": "DELETE",
    "path": "/v1/auth/sessions/{session_id}",
    "tag": "auth",
    "summary": "Revoke Session",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "session_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "verify_email_v1_auth_verify_email_post",
    "method": "POST",
    "path": "/v1/auth/verify-email",
    "tag": "auth",
    "summary": "Verify Email",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "VerifyEmailRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "forgot_password_v1_auth_forgot_password_post",
    "method": "POST",
    "path": "/v1/auth/forgot-password",
    "tag": "auth",
    "summary": "Forgot Password",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "PasswordResetRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "reset_password_v1_auth_reset_password_post",
    "method": "POST",
    "path": "/v1/auth/reset-password",
    "tag": "auth",
    "summary": "Reset Password",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": {
      "type": "PasswordResetConfirm",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_current_org_v1_organizations_current_get",
    "method": "GET",
    "path": "/v1/organizations/current",
    "tag": "organizations",
    "summary": "Get Current Org",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OrganizationResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "update_org_v1_organizations_current_patch",
    "method": "PATCH",
    "path": "/v1/organizations/current",
    "tag": "organizations",
    "summary": "Update Org",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "OrganizationUpdate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OrganizationResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_projects_v1_projects_get",
    "method": "GET",
    "path": "/v1/projects",
    "tag": "organizations",
    "summary": "List Projects",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "ProjectResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_project_v1_projects_post",
    "method": "POST",
    "path": "/v1/projects",
    "tag": "organizations",
    "summary": "Create Project",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "ProjectCreate",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "ProjectResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_project_detail_v1_projects__project_id__get",
    "method": "GET",
    "path": "/v1/projects/{project_id}",
    "tag": "organizations",
    "summary": "Get Project Detail",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "ProjectResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "update_project_v1_projects__project_id__patch",
    "method": "PATCH",
    "path": "/v1/projects/{project_id}",
    "tag": "organizations",
    "summary": "Update Project",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "ProjectUpdate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "ProjectResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_members_v1_members_get",
    "method": "GET",
    "path": "/v1/members",
    "tag": "organizations",
    "summary": "List Members",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "MemberResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "invite_member_v1_members_post",
    "method": "POST",
    "path": "/v1/members",
    "tag": "organizations",
    "summary": "Invite Member",
    "description": "Invite an existing user into this organization.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "MemberInvite",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "MemberResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "update_member_v1_members__membership_id__patch",
    "method": "PATCH",
    "path": "/v1/members/{membership_id}",
    "tag": "organizations",
    "summary": "Update Member",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "membership_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "MemberUpdate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "MemberResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "remove_member_v1_members__membership_id__delete",
    "method": "DELETE",
    "path": "/v1/members/{membership_id}",
    "tag": "organizations",
    "summary": "Remove Member",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "membership_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_keys_v1_keys_get",
    "method": "GET",
    "path": "/v1/keys",
    "tag": "organizations",
    "summary": "List Keys",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_ApiKeyResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_key_v1_projects__project_id__keys_post",
    "method": "POST",
    "path": "/v1/projects/{project_id}/keys",
    "tag": "organizations",
    "summary": "Create Key",
    "description": "Mint a key. The plaintext is returned exactly once and never stored.",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "ApiKeyCreate",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "ApiKeyCreated"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "rotate_key_v1_keys__key_id__rotate_post",
    "method": "POST",
    "path": "/v1/keys/{key_id}/rotate",
    "tag": "organizations",
    "summary": "Rotate Key",
    "description": "Issue a replacement. Both keys work during the grace window.",
    "deprecated": false,
    "parameters": [
      {
        "name": "key_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "ApiKeyRotate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "ApiKeyCreated"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "revoke_key_v1_keys__key_id__delete",
    "method": "DELETE",
    "path": "/v1/keys/{key_id}",
    "tag": "organizations",
    "summary": "Revoke Key",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "key_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "reason",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_credentials_v1_credentials_get",
    "method": "GET",
    "path": "/v1/credentials",
    "tag": "credentials",
    "summary": "List Credentials",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CredentialResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_credential_v1_credentials_post",
    "method": "POST",
    "path": "/v1/credentials",
    "tag": "credentials",
    "summary": "Create Credential",
    "description": "Encrypt, validate with one cheap upstream call, store the fingerprint.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "CredentialCreate",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "CredentialResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "validate_credential_v1_credentials__credential_id__validate_post",
    "method": "POST",
    "path": "/v1/credentials/{credential_id}/validate",
    "tag": "credentials",
    "summary": "Validate Credential",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "credential_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CredentialResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "rotate_credential_v1_credentials__credential_id__rotate_post",
    "method": "POST",
    "path": "/v1/credentials/{credential_id}/rotate",
    "tag": "credentials",
    "summary": "Rotate Credential",
    "description": "Encrypt, validate, atomically swap, grace the old, then destroy it.",
    "deprecated": false,
    "parameters": [
      {
        "name": "credential_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "CredentialRotate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CredentialResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "revoke_credential_v1_credentials__credential_id__delete",
    "method": "DELETE",
    "path": "/v1/credentials/{credential_id}",
    "tag": "credentials",
    "summary": "Revoke Credential",
    "description": "Revoke immediately.",
    "deprecated": false,
    "parameters": [
      {
        "name": "credential_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "trigger_reconcile_v1_credentials_reconcile_quota_post",
    "method": "POST",
    "path": "/v1/credentials/reconcile-quota",
    "tag": "credentials",
    "summary": "Trigger Reconcile",
    "description": "Queue an upstream quota reconciliation (section 40).",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "trigger_revalidate_v1_credentials_revalidate_post",
    "method": "POST",
    "path": "/v1/credentials/revalidate",
    "tag": "credentials",
    "summary": "Trigger Revalidate",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_plan_v1_plan_post",
    "method": "POST",
    "path": "/v1/plan",
    "tag": "search",
    "summary": "Create Plan",
    "description": "Plan without executing.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "PlanRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "PlanResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "search_v1_search_post",
    "method": "POST",
    "path": "/v1/search",
    "tag": "search",
    "summary": "Search",
    "description": "Plan with cache-aware marginal-cost replanning, then execute.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "SearchRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "SearchResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "run_v1_run_post",
    "method": "POST",
    "path": "/v1/run",
    "tag": "search",
    "summary": "Run",
    "description": "Alias of /search kept for API symmetry with /plan.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "SearchRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "SearchResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_runs_v1_runs_get",
    "method": "GET",
    "path": "/v1/runs",
    "tag": "runs",
    "summary": "List Runs",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "status",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "engine",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "changed_selection",
        "location": "query",
        "required": false,
        "type": "boolean",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_RunSummary_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_run_v1_runs__run_id__get",
    "method": "GET",
    "path": "/v1/runs/{run_id}",
    "tag": "runs",
    "summary": "Get Run",
    "description": "The Run Inspector payload: plan, candidates, steps, provenance, mode.",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "RunResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_run_plan_v1_runs__run_id__plan_get",
    "method": "GET",
    "path": "/v1/runs/{run_id}/plan",
    "tag": "runs",
    "summary": "Get Run Plan",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "PlanResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_step_payload_v1_runs__run_id__steps__step_id__payload_get",
    "method": "GET",
    "path": "/v1/runs/{run_id}/steps/{step_id}/payload",
    "tag": "runs",
    "summary": "Get Step Payload",
    "description": "Raw SERP payload, behind its own permission.",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "step_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "PayloadResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "stream_run_v1_runs__run_id__stream_get",
    "method": "GET",
    "path": "/v1/runs/{run_id}/stream",
    "tag": "runs",
    "summary": "Stream Run",
    "description": "Real backend stage transitions.",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "any"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "replay_v1_runs__run_id__replay_post",
    "method": "POST",
    "path": "/v1/runs/{run_id}/replay",
    "tag": "runs",
    "summary": "Replay",
    "description": "Re-run the same intent against current cache state.",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "SearchResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "report_false_hit_v1_runs__run_id__report_false_hit_post",
    "method": "POST",
    "path": "/v1/runs/{run_id}/report-false-hit",
    "tag": "runs",
    "summary": "Report False Hit",
    "description": "File a bad semantic hit from the Run Inspector (section 47).",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "FalseHitReportRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_catalog_v1_catalog_get",
    "method": "GET",
    "path": "/v1/catalog",
    "tag": "catalog",
    "summary": "Get Catalog",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "version",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "tag",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "search",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CatalogResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_versions_v1_catalog_versions_get",
    "method": "GET",
    "path": "/v1/catalog/versions",
    "tag": "catalog",
    "summary": "List Versions",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "get_engine_v1_catalog_engines__engine__get",
    "method": "GET",
    "path": "/v1/catalog/engines/{engine}",
    "tag": "catalog",
    "summary": "Get Engine",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "engine",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "version",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CatalogEngineView"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "engine_paths_v1_catalog_engines__engine__paths_get",
    "method": "GET",
    "path": "/v1/catalog/engines/{engine}/paths",
    "tag": "catalog",
    "summary": "Engine Paths",
    "description": "Every valid chain that reaches ``engine`` from the supplied parameters.",
    "deprecated": false,
    "parameters": [
      {
        "name": "engine",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "version",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "params",
        "location": "query",
        "required": false,
        "type": "string",
        "description": "Comma-separated available parameters"
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_tags_v1_catalog_tags_get",
    "method": "GET",
    "path": "/v1/catalog/tags",
    "tag": "catalog",
    "summary": "List Tags",
    "description": "Capability tags and their members. Engines sharing a tag compete.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "catalog_graph_v1_catalog_graph_get",
    "method": "GET",
    "path": "/v1/catalog/graph",
    "tag": "catalog",
    "summary": "Catalog Graph",
    "description": "Nodes plus both edge kinds, ready for the GSAP dependency graph.",
    "deprecated": false,
    "parameters": [
      {
        "name": "version",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_budgets_v1_budgets_get",
    "method": "GET",
    "path": "/v1/budgets",
    "tag": "governance",
    "summary": "List Budgets",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "BudgetOverview"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_budget_v1_budgets_post",
    "method": "POST",
    "path": "/v1/budgets",
    "tag": "governance",
    "summary": "Create Budget",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "BudgetCreate",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "BudgetResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "update_budget_v1_budgets__budget_id__patch",
    "method": "PATCH",
    "path": "/v1/budgets/{budget_id}",
    "tag": "governance",
    "summary": "Update Budget",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "budget_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "BudgetUpdate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "BudgetResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "delete_budget_v1_budgets__budget_id__delete",
    "method": "DELETE",
    "path": "/v1/budgets/{budget_id}",
    "tag": "governance",
    "summary": "Delete Budget",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "budget_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "cache_dashboard_v1_cache_get",
    "method": "GET",
    "path": "/v1/cache",
    "tag": "governance",
    "summary": "Cache Dashboard",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "days",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "CacheDashboardResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_cache_entries_v1_cache_entries_get",
    "method": "GET",
    "path": "/v1/cache/entries",
    "tag": "governance",
    "summary": "List Cache Entries",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "engine",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "project_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_CacheEntryResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_guard_rejections_v1_cache_guard_rejections_get",
    "method": "GET",
    "path": "/v1/cache/guard-rejections",
    "tag": "governance",
    "summary": "List Guard Rejections",
    "description": "Every near-match the entity/numeral guard rejected.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_GuardRejectionResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "invalidate_cache_v1_cache_invalidate_post",
    "method": "POST",
    "path": "/v1/cache/invalidate",
    "tag": "governance",
    "summary": "Invalidate Cache",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "project_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-SerpFlow-Project",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "CacheInvalidateRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "dashboard_v1_analytics_dashboard_get",
    "method": "GET",
    "path": "/v1/analytics/dashboard",
    "tag": "governance",
    "summary": "Dashboard",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "days",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "DashboardResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "savings_v1_analytics_savings_get",
    "method": "GET",
    "path": "/v1/analytics/savings",
    "tag": "governance",
    "summary": "Savings",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "days",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "SavingsDecompositionResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "attribution_v1_analytics_attribution_get",
    "method": "GET",
    "path": "/v1/analytics/attribution",
    "tag": "governance",
    "summary": "Attribution",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "days",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "routing_quality_v1_analytics_routing_get",
    "method": "GET",
    "path": "/v1/analytics/routing",
    "tag": "governance",
    "summary": "Routing Quality",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "volatility_v1_analytics_volatility_get",
    "method": "GET",
    "path": "/v1/analytics/volatility",
    "tag": "governance",
    "summary": "Volatility",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "days",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "engine_reach_v1_analytics_engine_reach_get",
    "method": "GET",
    "path": "/v1/analytics/engine-reach",
    "tag": "governance",
    "summary": "Engine Reach",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "cross_project_v1_analytics_cross_project_get",
    "method": "GET",
    "path": "/v1/analytics/cross-project",
    "tag": "governance",
    "summary": "Cross Project",
    "description": "Cross-project cache benefit (section 37).",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_benchmarks_v1_benchmarks_get",
    "method": "GET",
    "path": "/v1/benchmarks",
    "tag": "governance",
    "summary": "List Benchmarks",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "catalog_version",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "BenchmarkRunResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_benchmark_tasks_v1_benchmarks_tasks_get",
    "method": "GET",
    "path": "/v1/benchmarks/tasks",
    "tag": "governance",
    "summary": "List Benchmark Tasks",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "category",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_BenchmarkTaskResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_evals_v1_benchmarks__run_id__evals_get",
    "method": "GET",
    "path": "/v1/benchmarks/{run_id}/evals",
    "tag": "governance",
    "summary": "List Evals",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "run_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "RoutingEvalResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "run_benchmark_v1_benchmarks_run_post",
    "method": "POST",
    "path": "/v1/benchmarks/run",
    "tag": "governance",
    "summary": "Run Benchmark",
    "description": "Run the suite on demand.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "BenchmarkRunRequest",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "BenchmarkRunResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_audit_v1_audit_get",
    "method": "GET",
    "path": "/v1/audit",
    "tag": "governance",
    "summary": "List Audit",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "action",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "actor_id",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_AuditEntryResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "verify_audit_v1_audit_verify_get",
    "method": "GET",
    "path": "/v1/audit/verify",
    "tag": "governance",
    "summary": "Verify Audit",
    "description": "Walk the hash chain and report the first break, if any.",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "AuditVerifyResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "export_audit_v1_audit_export_get",
    "method": "GET",
    "path": "/v1/audit/export",
    "tag": "governance",
    "summary": "Export Audit",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_alerts_v1_alerts_get",
    "method": "GET",
    "path": "/v1/alerts",
    "tag": "governance",
    "summary": "List Alerts",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "status",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "limit",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "offset",
        "location": "query",
        "required": false,
        "type": "integer",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "Page_AlertResponse_"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "update_alert_v1_alerts__alert_id__patch",
    "method": "PATCH",
    "path": "/v1/alerts/{alert_id}",
    "tag": "governance",
    "summary": "Update Alert",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "alert_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "AlertUpdate",
      "required": true
    },
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "AlertResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "list_channels_v1_notification_channels_get",
    "method": "GET",
    "path": "/v1/notification-channels",
    "tag": "governance",
    "summary": "List Channels",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "NotificationChannelResponse[]"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "create_channel_v1_notification_channels_post",
    "method": "POST",
    "path": "/v1/notification-channels",
    "tag": "governance",
    "summary": "Create Channel",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": {
      "type": "NotificationChannelCreate",
      "required": true
    },
    "responses": [
      {
        "status": "201",
        "description": "Successful Response",
        "type": "NotificationChannelResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "delete_channel_v1_notification_channels__channel_id__delete",
    "method": "DELETE",
    "path": "/v1/notification-channels/{channel_id}",
    "tag": "governance",
    "summary": "Delete Channel",
    "description": "",
    "deprecated": false,
    "parameters": [
      {
        "name": "channel_id",
        "location": "path",
        "required": true,
        "type": "string",
        "description": ""
      },
      {
        "name": "access_token",
        "location": "query",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "authorization",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      },
      {
        "name": "X-API-Key",
        "location": "header",
        "required": false,
        "type": "string",
        "description": ""
      }
    ],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "OkResponse"
      },
      {
        "status": "422",
        "description": "Validation Error",
        "type": "HTTPValidationError"
      }
    ]
  },
  {
    "id": "healthz_healthz_get",
    "method": "GET",
    "path": "/healthz",
    "tag": "infrastructure",
    "summary": "Healthz",
    "description": "Liveness. Answers without touching any dependency.",
    "deprecated": false,
    "parameters": [],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "HealthResponse"
      }
    ]
  },
  {
    "id": "readyz_readyz_get",
    "method": "GET",
    "path": "/readyz",
    "tag": "infrastructure",
    "summary": "Readyz",
    "description": "Readiness. Checks every dependency the API actually needs.",
    "deprecated": false,
    "parameters": [],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "HealthResponse"
      }
    ]
  },
  {
    "id": "prometheus_metrics_metrics_get",
    "method": "GET",
    "path": "/metrics",
    "tag": "infrastructure",
    "summary": "Prometheus Metrics",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "any"
      }
    ]
  },
  {
    "id": "root__get",
    "method": "GET",
    "path": "/",
    "tag": "infrastructure",
    "summary": "Root",
    "description": "",
    "deprecated": false,
    "parameters": [],
    "body": null,
    "responses": [
      {
        "status": "200",
        "description": "Successful Response",
        "type": "object"
      }
    ]
  }
];
