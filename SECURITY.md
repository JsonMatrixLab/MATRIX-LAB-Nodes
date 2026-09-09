# Security

Do not include credentials, private prompts, workflows, local paths, provider response bodies, or private media in public reports.

`MATRIXLAB_PromptDirector` keeps provider credentials outside serialized workflows. Ordinary node execution returns saved text and makes no provider request. Only the explicit **Generate Prompt** action may send selected reference images and prompt fields to xAI. Review that request before authorizing provider use.

When reporting a vulnerability, use the repository's Security tab if private reporting is available. Otherwise, open a minimal issue containing no secrets, private data, or working exploit and request a private contact route.
