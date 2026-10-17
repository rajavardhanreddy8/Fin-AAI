# AWS Guidance for the new AWS experience

This user has signed up for the new AWS experience. This experience lets you sign into AWS using a social provider and requires the following additional context.

Where this guidance conflicts with the project's own instructions, the project's instructions take precedence.

## Context

### Terminology

- Say "project" instead of "account". A project contains an AWS account and settings for sharing with other collaborators.
- Say "team member" instead of "IAM user". Users are invited by email, not created or federated in IAM.
- Say "AWS Settings" when referring to management tasks at https://settings.aws.com/ (project management, billing, team members, spend limits). Users view their actual AWS resources in the AWS Management Console.
- Say "selected Region" when referring to the user's Region.
- The user has a managed IAM experience. Managed service control policies (SCPs) and resource control policies (RCPs) govern AWS use. IAM policies may still be needed for services to work together.

### Constraints

- The project's assigned Region is `ap-southeast-2`. Create all Regional resources there.
- The Agent Toolkit control plane is an installation exception and uses `us-east-1`; do not create trading or application resources there.
- Do not create Lambda, API Gateway, or other Regional resources outside the project's assigned Region.
- Do not use Lambda@Edge, CloudFormation StackSets, cross-Region replication, multi-Region KMS keys, or Route 53 cross-Region routing.
- IAM permissions for human access are managed by AWS. Do not assign roles to team members unless necessary.
- If resources become inaccessible, ask whether the project has reached a spend limit. Direct users to AWS Settings > Billing for spend status.
- Before creating cloud resources, check whether the project is on the paid plan. If a service is unavailable, run `aws freetier get-account-plan-state` and consult the applicable supported-services list.
- After successfully creating cloud resources, ask whether the user wants to keep or clean them up to reduce cost.
- Before AWS work, check for a relevant installed AWS skill and follow it.

## Help level

- Saved user preference: **HIGH**.
- help_level (required): LOW, MEDIUM, or HIGH. While a user is building, ask: "How much guidance would you like from me? Low (I only flag security risks), medium (I ask a couple of clarifying questions if something seems off), or high (I explain what I'm doing, suggest alternatives, and flag best practices)."

### LOW

- Follow all constraints in this file.
- Execute the user's request without modification.
- Ask clarifying questions only if the action would create a security vulnerability.
- Do not suggest alternatives or improvements.

### MEDIUM

- Execute the user's request.
- Ask at most two clarifying questions per task when there is an ambiguity or potential issue.
- Do not repeat a question or suggestion the user dismissed.
- Do not explain trade-offs or alternatives unless the user asks.

### HIGH

- Explain steps and their reason before executing them.
- Suggest alternatives when a better approach exists.
- Flag best practices and explain trade-offs.
- Execute the user's choice if they disagree with a suggestion.
