import {Construct} from "constructs";
import * as path from "path";

import {Duration, RemovalPolicy, Stack, StackProps} from "aws-cdk-lib";
import {IStringParameter} from "aws-cdk-lib/aws-ssm";
import {Certificate, DnsValidatedCertificate} from "aws-cdk-lib/aws-certificatemanager";
import {
    Distribution,
    Function as CfFunction,
    FunctionCode,
    FunctionEventType,
    PriceClass,
    SecurityPolicyProtocol,
    ViewerProtocolPolicy,
} from "aws-cdk-lib/aws-cloudfront";
import {S3BucketOrigin} from "aws-cdk-lib/aws-cloudfront-origins";
import {HostedZone, IHostedZone, RecordSet, RecordTarget, RecordType} from "aws-cdk-lib/aws-route53";
import {CloudFrontTarget} from "aws-cdk-lib/aws-route53-targets";
import {BlockPublicAccess, Bucket} from "aws-cdk-lib/aws-s3";
import {BucketDeployment, Source} from "aws-cdk-lib/aws-s3-deployment";

import {BASE_DOMAIN, HOSTED_ZONE_ID, StageType} from "../config";

export interface FrontendStackProps extends StackProps {
    stageType: StageType;
    authApiDomain: string;
    oidcProviderUrl: IStringParameter;
    clientId: IStringParameter;
}

export class FrontendStack extends Stack {
    private readonly props: FrontendStackProps;

    private readonly hostedZone: IHostedZone;
    private readonly bucket: Bucket;
    private readonly certificate: Certificate;
    public readonly distribution: Distribution;

    private get domainName(): string {
        return `${this.props.stageType.toLowerCase()}.${BASE_DOMAIN}`;
    }

    constructor(scope: Construct, id: string, props: FrontendStackProps) {
        super(scope, id, props);
        this.props = props;

        this.hostedZone = HostedZone.fromHostedZoneAttributes(this, "HostedZone", {
            hostedZoneId: HOSTED_ZONE_ID,
            zoneName: BASE_DOMAIN,
        });
        this.bucket = this.buildBucket()
        this.certificate = this.buildCertificate();

        this.distribution = this.buildDistribution();
    }

    private buildBucket(): Bucket {
        return new Bucket(this, "FrontendBucket", {
            bucketName: `ffsync-frontend-${this.props.stageType.toLowerCase()}`,
            blockPublicAccess: BlockPublicAccess.BLOCK_ALL,
            versioned: true,
            removalPolicy: RemovalPolicy.DESTROY,
            autoDeleteObjects: true,
        });
    }

    private buildCertificate(): Certificate {
        // DnsValidatedCertificate is deprecated but required here for cross-region
        // certificate creation in a single stack. CloudFront requires us-east-1.
        // TODO: Migrate to a separate us-east-1 certificate stack when upgrading CDK.
        return new DnsValidatedCertificate(this, "Certificate", {
            domainName: this.domainName,
            hostedZone: this.hostedZone,
            region: "us-east-1",
        });
    }

    private buildDistribution(): Distribution {
        const configJson = JSON.stringify({
            auth_server_base_url: `https://${this.props.authApiDomain}`,
            oauth_server_base_url: `https://${this.props.authApiDomain}`,
            profile_server_base_url: `https://${this.props.authApiDomain}`,
            sync_tokenserver_base_url: `https://${this.props.authApiDomain}`,
            content_url: `https://${this.domainName}`,
        });

        const wellKnownFn = new CfFunction(this, "WellKnownFunction", {
            code: FunctionCode.fromInline([
                "function handler(event) {",
                "  if (event.request.uri === '/.well-known/fxa-client-configuration') {",
                "    return {",
                "      statusCode: 200,",
                "      statusDescription: 'OK',",
                "      headers: {",
                "        'content-type': { value: 'application/json' },",
                "        'cache-control': { value: 'public, max-age=3600' }",
                "      },",
                `      body: '${configJson}'`,
                "    };",
                "  }",
                "  return event.request;",
                "}",
            ].join("\n")),
        });

        const distribution = new Distribution(this, "Distribution", {
            defaultBehavior: {
                origin: S3BucketOrigin.withOriginAccessControl(this.bucket),
                viewerProtocolPolicy: ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                functionAssociations: [{
                    function: wellKnownFn,
                    eventType: FunctionEventType.VIEWER_REQUEST,
                }],
            },
            domainNames: [this.domainName],
            certificate: this.certificate,
            defaultRootObject: "index.html",
            minimumProtocolVersion: SecurityPolicyProtocol.TLS_V1_2_2021,
            priceClass: PriceClass.PRICE_CLASS_100,
            errorResponses: [
                {
                    httpStatus: 403,
                    responseHttpStatus: 200,
                    responsePagePath: "/index.html",
                    ttl: Duration.seconds(0),
                },
                {
                    httpStatus: 404,
                    responseHttpStatus: 200,
                    responsePagePath: "/index.html",
                    ttl: Duration.seconds(0),
                },
            ],
        });


        [RecordType.A, RecordType.AAAA].map((recordType) => {
            new RecordSet(this, `${recordType}RecordSet`, {
                recordType,
                zone: this.hostedZone,
                recordName: this.domainName,
                target: RecordTarget.fromAlias(new CloudFrontTarget(distribution)),
            });
        });

        new BucketDeployment(this, "DeployFrontend", {
            sources: [
                Source.asset(path.join(__dirname, "../../frontend/dist")),
                Source.jsonData("config.json", {
                    oidcProviderUrl: this.props.oidcProviderUrl.stringValue,
                    clientId: this.props.clientId.stringValue,
                    redirectUri: `https://${this.domainName}`,
                    authServerUrl: `https://${this.props.authApiDomain}`,
                    scopes: ["openid", "profile", "email"],
                }),
            ],
            destinationBucket: this.bucket,
            distribution,
            distributionPaths: ["/*"],
        });
        return distribution;
    }
}
