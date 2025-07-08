import { Stack, StackProps } from "aws-cdk-lib";
import { EndpointType, RestApi } from "aws-cdk-lib/aws-apigateway";
import { Certificate } from "aws-cdk-lib/aws-certificatemanager";
import { Construct } from "constructs";

export interface ServiceStackProps extends StackProps {
    stage: string;
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
        const domainName = `${this.props.stage}.ffsync.layertwo.dev`;
        const certificate = new Certificate(this, "Certificate", {domainName});
        return new RestApi(this, 'Api', {
            // TODO migrate to EDGE, but need to put cert in IAD
            endpointTypes: [EndpointType.REGIONAL],
            restApiName: `ffsync-${this.props.stage}`,
            domainName: {
                domainName,
                certificate,
            }
        });
    }
}
