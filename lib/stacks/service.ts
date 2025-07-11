import {Construct} from "constructs";

import {Stack, StackProps} from "aws-cdk-lib";
import {
    AuthorizationType,
    EndpointType,
    MockIntegration,
    PassthroughBehavior,
    RestApi,
    SecurityPolicy,
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
    private readonly api: RestApi;

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        this.props = props;
        this.api = this.buildApi();
    }

    private buildApi(): RestApi {
        const hostedZone = HostedZone.fromHostedZoneAttributes(this, "HostedZone", {
            hostedZoneId: HOSTED_ZONE_ID,
            zoneName: BASE_DOMAIN,
        });
        const domainName = `${this.props.stageType}.${BASE_DOMAIN}`;
        const certificate = new Certificate(this, "Certificate", {
            domainName,
            validation: CertificateValidation.fromDns(hostedZone),
        });
        const api = new RestApi(this, "Api", {
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
}
