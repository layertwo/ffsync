import {Construct} from "constructs";

import {Stack, StackProps} from "aws-cdk-lib";
import {HostedZone} from "aws-cdk-lib/aws-route53";

import {BASE_DOMAIN} from "../config";

export class DnsStack extends Stack {
    private readonly props: StackProps;
    readonly hostedZone: HostedZone;

    constructor(scope: Construct, id: string, props: StackProps) {
        super(scope, id, props);

        this.props = props;

        this.hostedZone = new HostedZone(this, "Zone", {zoneName: BASE_DOMAIN});
    }
}
