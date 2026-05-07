# Guidelines
- Always use azure free tier resources when available. If free tier resources are not sufficient for the task, ask user for approval before provisioning paid resources.
- Always use consumption-based Azure resources. If fixed-cost resources are needed, ask user for approval before provisioning.
- For resources that can be scaled to zero, prefer that configuration to minimize costs when idle. Should let the user know if a resource cannot be scaled to zero and provide an estimated cost when idle.