import {PythonFunction} from "@aws-cdk/aws-lambda-python-alpha";
import {Construct} from "constructs";
import {readFileSync} from "fs";
import * as path from "path";

import {Duration, Stack, StackProps} from "aws-cdk-lib";
import {ApiDefinition, EndpointType, SecurityPolicy, SpecRestApi} from "aws-cdk-lib/aws-apigateway";
import {Certificate, CertificateValidation} from "aws-cdk-lib/aws-certificatemanager";
import {Architecture, Runtime} from "aws-cdk-lib/aws-lambda";
import {ARecord, HostedZone, RecordTarget} from "aws-cdk-lib/aws-route53";
import {ApiGateway} from "aws-cdk-lib/aws-route53-targets";

import {BASE_DOMAIN, HOSTED_ZONE_ID, StageType} from "../config";
import { Role, ServicePrincipal } from "aws-cdk-lib/aws-iam";

export interface ServiceStackProps extends StackProps {
    stageType: StageType;
}

export class ServiceStack extends Stack {
    private readonly props: ServiceStackProps;
    private readonly apiHandler: PythonFunction;
    private readonly apiRole: Role;
    private readonly api: SpecRestApi;

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        this.props = props;
        this.apiRole = this.buildApiRole();
        this.apiHandler = this.buildApiHandler();
        this.api = this.buildApi();
    }

    private buildApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "ApiHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/main.py",
            runtime: Runtime.PYTHON_3_12,
            architecture: Architecture.ARM_64,
            handler: "lambda_handler",
            functionName: `ffsync-storage-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
            },
        });
        fn.grantInvoke(this.apiRole);
        return fn;
    }

    private buildApiRole(): Role {
        return new Role(this, "ApiRole", {
            roleName: `ffsync-api-role-${this.props.stageType.toLowerCase()}`,
            assumedBy: new ServicePrincipal("apigateway.amazonaws.com"),
            description: `Role for API Gateway to invoke Lambda for stage ${this.props.stageType}`,
        });
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
        api.node.addDependency(this.apiHandler);

        new ARecord(this, "ARecord", {
            zone: hostedZone,
            recordName: domainName,
            target: RecordTarget.fromAlias(new ApiGateway(api)),
        });
        return api;
    }

    private get openApiSpec(): any {
        let openApiJson = readFileSync(
            path.join(__dirname, "../../build/smithy/source/openapi/StorageService.openapi.json"),
            "utf8",
        );

        // Replace placeholder with actual Lambda ARN
        openApiJson = openApiJson.replace(/CDK_LAMBDA_FUNCTION_ARN/g, this.apiHandler.functionArn);
        openApiJson = openApiJson.replace(/CDK_API_ROLE_ARN/g, this.apiRole.roleArn);

        return JSON.parse(openApiJson);
    }
}
