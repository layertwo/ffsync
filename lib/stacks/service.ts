import {Construct} from "constructs";
import {readFileSync} from "fs";
import * as path from "path";

import {Stack, StackProps} from "aws-cdk-lib";
import {
    ApiDefinition,
    AuthorizationType,
    EndpointType,
    MockIntegration,
    PassthroughBehavior,
    SecurityPolicy,
    SpecRestApi,
} from "aws-cdk-lib/aws-apigateway";
import {Certificate, CertificateValidation} from "aws-cdk-lib/aws-certificatemanager";
import {ARecord, HostedZone, RecordTarget} from "aws-cdk-lib/aws-route53";
import {ApiGateway} from "aws-cdk-lib/aws-route53-targets";

import {BASE_DOMAIN, HOSTED_ZONE_ID, StageType} from "../config";

export interface ServiceStackProps extends StackProps {
    stageType: StageType;
}

export class ServiceStack extends Stack {
    private readonly props: ServiceStackProps;
    private readonly api: SpecRestApi;

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        this.props = props;
        this.api = this.buildApi();
    }

    private buildApi(): SpecRestApi {
        const hostedZone = HostedZone.fromHostedZoneAttributes(this, "HostedZone", {
            hostedZoneId: HOSTED_ZONE_ID,
            zoneName: BASE_DOMAIN,
        });
        const domainName = `${this.props.stageType}.${BASE_DOMAIN}`;
        const certificate = new Certificate(this, "Certificate", {
            domainName,
            validation: CertificateValidation.fromDns(hostedZone),
        });
        const api = new SpecRestApi(this, "Api", {
            apiDefinition: ApiDefinition.fromInline(this.openApiSpec),
            endpointTypes: [EndpointType.EDGE],
            restApiName: `ffsync-${this.props.stageType}`,
            domainName: {
                domainName,
                certificate,
                securityPolicy: SecurityPolicy.TLS_1_2,
            },
            deployOptions: {
                stageName: this.props.stageType.toLowerCase(),
            },
            disableExecuteApiEndpoint: true,
        });

        api.root.addMethod(
            "GET",
            new MockIntegration({
                integrationResponses: [{statusCode: "200"}],
                passthroughBehavior: PassthroughBehavior.NEVER,
                requestTemplates: {
                    "application/json": '{ "statusCode": 200 }',
                },
            }),
            {
                methodResponses: [{statusCode: "200"}],
                authorizationType: AuthorizationType.IAM,
            },
        );
        new ARecord(this, "ARecord", {
            zone: hostedZone,
            recordName: domainName,
            target: RecordTarget.fromAlias(new ApiGateway(api)),
        });
        return api;
    }

    private get openApiSpec(): string {
        const openapi = JSON.parse(
            readFileSync(
                path.join(
                    __dirname,
                    "../../smithy/build/smithy/source/openapi/StorageService.openapi.json",
                ),
                "utf8",
            ),
        );
        return openapi;
    }
}
