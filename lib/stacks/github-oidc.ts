import {Construct} from "constructs";

import {CfnOutput, Duration, Stack, StackProps} from "aws-cdk-lib";
import {
    Effect,
    OpenIdConnectProvider,
    PolicyStatement,
    Role,
    WebIdentityPrincipal,
} from "aws-cdk-lib/aws-iam";

export interface GitHubOidcStackProps extends StackProps {
    readonly githubOrg: string;
    readonly githubRepo: string;
    readonly githubBranch?: string;
    readonly githubEnvironment?: string;
}

// Reference: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws
export class GitHubOidcStack extends Stack {
    public readonly role: Role;

    constructor(scope: Construct, id: string, props: GitHubOidcStackProps) {
        super(scope, id, props);

        // Create or reference the GitHub OIDC provider
        const githubProvider = new OpenIdConnectProvider(this, "GitHubOidcProvider", {
            url: "https://token.actions.githubusercontent.com",
            clientIds: ["sts.amazonaws.com"],
        });

        // Build the subject claim for the trust policy
        let subjectClaim = `repo:${props.githubOrg}/${props.githubRepo}:`;

        if (props.githubEnvironment) {
            subjectClaim += `environment:${props.githubEnvironment}`;
        } else if (props.githubBranch) {
            subjectClaim += `ref:refs/heads/${props.githubBranch}`;
        } else {
            // Allow any branch/environment
            subjectClaim += "*";
        }

        // Create IAM role that GitHub Actions can assume
        this.role = new Role(this, "GitHubActionsRole", {
            roleName: "GitHubActionsDeployRole",
            assumedBy: new WebIdentityPrincipal(githubProvider.openIdConnectProviderArn, {
                StringEquals: {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                },
                StringLike: {
                    "token.actions.githubusercontent.com:sub": subjectClaim,
                },
            }),
            maxSessionDuration: Duration.hours(1),
        });

        this.role.addToPolicy(
            new PolicyStatement({
                effect: Effect.ALLOW,
                actions: ["sts:AssumeRole"],
                resources: ["*"],
                conditions: {
                    StringEquals: {
                        "iam:ResourceTag/aws-cdk:bootstrap-role": [
                            "deploy",
                            "file-publishing",
                            "image-publishing",
                            "lookup",
                        ],
                    },
                },
            }),
        );

        // Output the role ARN for use in GitHub secrets
        new CfnOutput(this, "GitHubActionsRoleArn", {
            value: this.role.roleArn,
            description:
                "ARN of the IAM role for GitHub Actions (add to GitHub secrets as AWS_ROLE_ARN)",
            exportName: "GitHubActionsRoleArn",
        });

        // Output the OIDC provider ARN
        new CfnOutput(this, "GitHubOidcProviderArn", {
            value: githubProvider.openIdConnectProviderArn,
            description: "ARN of the GitHub OIDC provider",
        });
    }
}
