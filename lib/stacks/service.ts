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
import {Architecture, IFunction, Runtime} from "aws-cdk-lib/aws-lambda";
import {
    HostedZone,
    IHostedZone,
    RecordSet,
    RecordTarget,
    RecordType,
} from "aws-cdk-lib/aws-route53";
import {ApiGateway} from "aws-cdk-lib/aws-route53-targets";

import {BASE_DOMAIN, HOSTED_ZONE_ID, StageType} from "../config";
import {Service} from "../config/service";
import {capitalCase} from "../utils";

export interface ServiceStackProps extends StackProps {
    stageType: StageType;
}

export class ServiceStack extends Stack {
    private readonly props: ServiceStackProps;

    private readonly hostedZone: IHostedZone;
    private readonly apiExecuteRole: Role;

    // Token Service
    public readonly tokenHandler: IFunction;
    public readonly tokenApi: SpecRestApi;

    // Storage Service
    public readonly storageTable: Table;
    public readonly storageHandler: IFunction;
    public readonly storageApi: SpecRestApi;

    constructor(scope: Construct, id: string, props: ServiceStackProps) {
        super(scope, id, props);

        this.props = props;

        this.hostedZone = HostedZone.fromHostedZoneAttributes(this, "HostedZone", {
            hostedZoneId: HOSTED_ZONE_ID,
            zoneName: BASE_DOMAIN,
        });
        this.apiExecuteRole = this.buildApiExecuteRole();

        // Token Service
        this.tokenHandler = this.buildTokenApiHandler();
        this.tokenApi = this.buildApi(Service.TOKEN, this.tokenHandler);

        // Storage Service
        this.storageTable = this.buildStorageTable();
        this.storageHandler = this.buildStorageApiHandler();
        this.storageApi = this.buildApi(Service.STORAGE, this.storageHandler);
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

    private buildStorageApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "ApiHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/__init__.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "storage_api_handler",
            functionName: `ffsync-storage-api-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            memorySize: 512,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
                STORAGE_TABLE_NAME: this.storageTable.tableName,
            },
        });

        // Grant DynamoDB permissions to Lambda
        this.storageTable.grantReadWriteData(fn);
        fn.grantInvoke(this.apiExecuteRole);
        this.exportValue(fn.functionName);

        return fn;
    }

    private buildTokenApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "TokenApiHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/__init__.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "token_api_handler",
            functionName: `ffsync-token-api-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            memorySize: 512,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
            },
        });

        fn.grantInvoke(this.apiExecuteRole);

        return fn;
    }

    private buildApiExecuteRole(): Role {
        return new Role(this, "ApiRole", {
            roleName: `ffsync-api-role-${this.props.stageType.toLowerCase()}`,
            assumedBy: new ServicePrincipal("apigateway.amazonaws.com"),
            description: `Role for API Gateway to invoke Lambda for stage ${this.props.stageType}`,
        });
    }

    private buildApi(service: Service, handler: IFunction): SpecRestApi {
        const capitalService = capitalCase(service);
        const domainName = `${service.toLowerCase()}.${this.props.stageType}.${BASE_DOMAIN}`;
        const certificate = new Certificate(this, `${capitalService}Certificate`, {
            domainName,
            validation: CertificateValidation.fromDns(this.hostedZone),
        });

        const openApiSpec = this.buildOpenApiSpec(service, handler);
        const api = new SpecRestApi(this, `${capitalService}Api`, {
            apiDefinition: ApiDefinition.fromInline(openApiSpec),
            endpointTypes: [EndpointType.EDGE],
            restApiName: `ffsync-${service.toLowerCase()}-${this.props.stageType}`,
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
        api.node.addDependency(handler);

        [RecordType.A, RecordType.AAAA].map((recordType) => {
            new RecordSet(this, `${capitalService}${recordType}RecordSet`, {
                recordType,
                zone: this.hostedZone,
                recordName: domainName,
                target: RecordTarget.fromAlias(new ApiGateway(api)),
            });
        });
        return api;
    }

    private buildOpenApiSpec(service: Service, handler: IFunction): any {
        const capitalService = capitalCase(service);
        let openApiJson = readFileSync(
            path.join(
                __dirname,
                // eslint-disable-next-line max-len
                `../../build/smithy/${service.toLowerCase()}/openapi/${capitalService}Service.openapi.json`,
            ),
            "utf8",
        );

        openApiJson = openApiJson.replace(/CDK_LAMBDA_FUNCTION_ARN/g, handler.functionArn);
        openApiJson = openApiJson.replace(/CDK_API_ROLE_ARN/g, this.apiExecuteRole.roleArn);

        return JSON.parse(openApiJson);
    }
}
