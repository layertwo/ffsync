import {DnsValidatedCertificate} from "@trautonen/cdk-dns-validated-certificate";
import {Construct} from "constructs";

import {Stack, StackProps} from "aws-cdk-lib";
import {
    AuthorizationType,
    EndpointType,
    MockIntegration,
    PassthroughBehavior,
    RestApi,
} from "aws-cdk-lib/aws-apigateway";
import {HostedZone} from "aws-cdk-lib/aws-route53";

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
        const certificate = new DnsValidatedCertificate(this, "Certificate", {
            domainName,
            validationHostedZones: [{hostedZone}],
            certificateRegion: "us-east-1",
        });
        const api = new RestApi(this, "Api", {
            endpointTypes: [EndpointType.EDGE],
            endpointConfiguration: {
                types: [EndpointType.EDGE],
            },
            restApiName: `ffsync-${this.props.stageType}`,
            domainName: {
                domainName,
                certificate,
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
        return api;
    }
}
