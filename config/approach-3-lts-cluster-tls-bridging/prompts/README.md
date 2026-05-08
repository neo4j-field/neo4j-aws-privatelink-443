# Prompts and Design Intent

This folder captures the prompts and decision points behind the cluster variant of approach-3. Per the project's reproducibility standard, the prompts that built the configs live alongside the configs.

| File | Purpose |
|---|---|
| `initial_request.md` | The original ask: collapse two-FQDN client routing to a single hostname on a 3-node cluster. |
| `rollout_decisions.md` | Decisions made during the rollout — naming, default_advertised_address handling, validation strategy, SELinux booleans. |
