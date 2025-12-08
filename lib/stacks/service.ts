import {PythonFunction} from "@aws-cdk/aws-lambda-python-alpha";
import {Construct} from "constructs";
import {readFileSync} from "fs";
import * as path from "path";

import {Duration, RemovalPolicy, Stack, StackProps} from "aws-cdk-lib";
import {
    ApiDefinition,
    EndpointType,
    MethodLoggingLevel,
    SecurityPolicy,
    SpecRestApi,
} from "aws-cdk-lib/aws-apigateway";
import {Certificate, CertificateValidation} from "aws-cdk-lib/aws-certificatemanager";
import {AttributeType, BillingMode, Table, TableEncryption} from "aws-cdk-lib/aws-dynamodb";
import {Role, ServicePrincipal} from "aws-cdk-lib/aws-iam";
import {Architecture, Runtime} from "aws-cdk-lib/aws-lambda";
import {ARecord, HostedZone, RecordTarget} from "aws-cdk-lib/aws-route53";
import {ApiGateway} from "aws-cdk-lib/aws-route53-targets";

import {BASE_DOMAIN, HOSTED_ZONE_ID, StageType} from "../config";

export interface ServiceStackProps extends StackProps {
    stageType: StageType;
}

export class ServiceStack extends Stack {
    private readonly props: ServiceStackProps;
    private readonly apiRole: Role;

    public readonly storageTable: Table;
    public readonly apiHandler: PythonFunction;
    public readonly api: SpecRestApi;

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        this.props = props;
        this.storageTable = this.buildStorageTable();
        this.apiRole = this.buildApiRole();
        this.apiHandler = this.buildApiHandler();
        this.api = this.buildApi();
    }

    private buildStorageTable(): Table {
        return new Table(this, "StorageTable", {
            tableName: `ffsync-storage-${this.props.stageType.toLowerCase()}`,
            encryption: TableEncryption.AWS_MANAGED,
            partitionKey: {
                name: "PK",
                type: AttributeType.STRING,
            },
            sortKey: {
                name: "SK",
                type: AttributeType.STRING,
            },
            billingMode: BillingMode.PAY_PER_REQUEST,
            pointInTimeRecoverySpecification: {
                pointInTimeRecoveryEnabled: true,
            },
            removalPolicy:
                this.props.stageType === StageType.PROD
                    ? RemovalPolicy.RETAIN
                    : RemovalPolicy.DESTROY,
        });
    }

    private buildApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "ApiHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/main.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "lambda_handler",
            functionName: `ffsync-storage-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            memorySize: 512,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
                STORAGE_TABLE_NAME: this.storageTable.tableName,
            },
        });

        // Grant DynamoDB permissions to Lambda
        this.storageTable.grantReadWriteData(fn);
        fn.grantInvoke(this.apiRole);
        this.exportValue(fn.functionName);

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
                metricsEnabled: true,
                loggingLevel: MethodLoggingLevel.INFO,
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
            path.join(__dirname, "../../build/smithy/storage/openapi/StorageService.openapi.json"),
            "utf8",
        );

        // Replace placeholder with actual Lambda ARN
        openApiJson = openApiJson.replace(/CDK_LAMBDA_FUNCTION_ARN/g, this.apiHandler.functionArn);
        openApiJson = openApiJson.replace(/CDK_API_ROLE_ARN/g, this.apiRole.roleArn);

        return JSON.parse(openApiJson);
    }
}
