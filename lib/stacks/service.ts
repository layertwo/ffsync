import {Construct} from "constructs";

import {Stack, StackProps} from "aws-cdk-lib";
import {
    AuthorizationType,
    EndpointType,
    MockIntegration,
    PassthroughBehavior,
    RestApi,
} from "aws-cdk-lib/aws-apigateway";
import {Certificate} from "aws-cdk-lib/aws-certificatemanager";

import {StageType} from "../config";

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
        const domainName = `${this.props.stageType}.ffsync.layertwo.dev`;
        const certificate = new Certificate(this, "Certificate", {domainName});
        const api = new RestApi(this, "Api", {
            // TODO migrate to EDGE, but need to put cert in IAD
            endpointTypes: [EndpointType.REGIONAL],
            restApiName: `ffsync-${this.props.stageType}`,
            domainName: {
                domainName,
                certificate,
            },
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
