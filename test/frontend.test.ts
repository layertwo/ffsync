import * as fs from "fs";
import * as path from "path";

import {App, Stack} from "aws-cdk-lib";
import {Template} from "aws-cdk-lib/assertions";
import {StringParameter} from "aws-cdk-lib/aws-ssm";

import {StageType} from "../lib/config";
import {FrontendStack} from "../lib/stacks/frontend";

const distDir = path.join(__dirname, "../frontend/dist");

beforeAll(() => {
    // Source.asset requires the directory to exist with at least one file.
    fs.mkdirSync(distDir, {recursive: true});
    fs.writeFileSync(path.join(distDir, "index.html"), "<html></html>");
});

afterAll(() => {
    fs.rmSync(distDir, {recursive: true, force: true});
});

describe("FrontendStack", () => {
    test("synthesizes expected resources", () => {
        const app = new App();
        const helperStack = new Stack(app, "HelperStack", {
            env: {account: "123456789012", region: "us-west-2"},
        });
        const stack = new FrontendStack(app, "TestFrontend", {
            env: {account: "123456789012", region: "us-west-2"},
            stageType: StageType.PROD,
            authApiDomain: "api.example.com",
            oidcProviderUrl: StringParameter.fromStringParameterName(helperStack, "OidcParam", "/test/oidc-url"),
            clientId: StringParameter.fromStringParameterName(helperStack, "ClientIdParam", "/test/client-id"),
        });

        const template = Template.fromStack(stack);

        template.resourceCountIs("AWS::S3::Bucket", 1);
        template.resourceCountIs("AWS::CloudFront::Distribution", 1);
        template.resourceCountIs("AWS::Route53::RecordSet", 2);

        template.hasResourceProperties("AWS::S3::Bucket", {
            BucketName: "ffsync-frontend-prod",
            PublicAccessBlockConfiguration: {
                BlockPublicAcls: true,
                BlockPublicPolicy: true,
                IgnorePublicAcls: true,
                RestrictPublicBuckets: true,
            },
            VersioningConfiguration: {
                Status: "Enabled",
            },
        });

        template.hasResourceProperties("AWS::CloudFront::Distribution", {
            DistributionConfig: {
                DefaultRootObject: "index.html",
                PriceClass: "PriceClass_100",
            },
        });

        // DnsValidatedCertificate creates a custom resource instead of a native
        // AWS::CertificateManager::Certificate resource.
        template.hasResourceProperties("AWS::CloudFormation::CustomResource", {
            DomainName: "prod.ffsync.layertwo.dev",
            Region: "us-east-1",
        });
    });
});
