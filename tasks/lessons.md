# Lessons

- When verification is blocked by missing runtime config, re-check the workspace for a newly added `.env` or equivalent before assuming the run must stay partial.
- For OpsBob, run direct API verification before browser-level product checks so runtime integration defects are isolated before UI debugging.
- IBM watsonx.ai and Orchestrate do not accept the raw IBM Cloud API key as the Bearer token; always exchange it for an IAM access token first.
- PATCHing watsonx project metadata to add compute details is not enough to satisfy foundation-model generation; the WML runtime must be associated to the project through the supported IBM UI/service integration flow or replaced with a valid `space_id` path.