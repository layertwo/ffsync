import { CfnOutput, Stack, StackProps } from "aws-cdk-lib";
import { Construct } from "constructs";

export interface ServiceStackProps extends StackProps {
    stage: string;
}

export class ServiceStack extends Stack {

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        new CfnOutput(this, "Sample", {value: props.stage});

    }
}
