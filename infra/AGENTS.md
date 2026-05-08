# Guidelines
- Always use azure free tier resources when available. If free tier resources are not sufficient for the task, ask user for approval before provisioning paid resources.
- Always use consumption-based Azure resources. If fixed-cost resources are needed, ask user for approval before provisioning.
- For resources that can be scaled to zero, prefer that configuration to minimize costs when idle. Should let the user know if a resource cannot be scaled to zero and provide an estimated cost when idle.
- Run Terraform locally only for bootstrap tasks under `infra/terraform/bootstrap`.
- Do not deploy or modify the dev stack with local Terraform. Dev stack changes should go through GitHub Actions only.
- When working on dev infrastructure, update the Terraform modules and the GitHub workflow inputs rather than applying the dev stack locally.
