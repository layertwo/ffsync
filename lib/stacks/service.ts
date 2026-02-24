import {PythonFunction} from "@aws-cdk/aws-lambda-python-alpha";
import {Construct} from "constructs";
import {readFileSync} from "fs";
import * as path from "path";

import {Duration, RemovalPolicy, Stack, StackProps} from "aws-cdk-lib";
import {
    AccessLogFormat,
    ApiDefinition,
    EndpointType,
    LogGroupLogDestination,
    MethodLoggingLevel,
    SecurityPolicy,
    SpecRestApi,
} from "aws-cdk-lib/aws-apigateway";
import {Certificate, CertificateValidation} from "aws-cdk-lib/aws-certificatemanager";
import {
    AttributeType,
    BillingMode,
    ProjectionType,
    Table,
    TableEncryption,
} from "aws-cdk-lib/aws-dynamodb";
import {Role, ServicePrincipal} from "aws-cdk-lib/aws-iam";
import {Architecture, IFunction, Runtime} from "aws-cdk-lib/aws-lambda";
import {LogGroup, RetentionDays} from "aws-cdk-lib/aws-logs";
import {
    HostedZone,
    IHostedZone,
    RecordSet,
    RecordTarget,
    RecordType,
} from "aws-cdk-lib/aws-route53";
import {ApiGateway} from "aws-cdk-lib/aws-route53-targets";
import {Secret} from "aws-cdk-lib/aws-secretsmanager";

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

    private get stageBaseDomain(): string {
        return `${this.props.stageType.toLowerCase()}.${BASE_DOMAIN}`;
    }

    // Token Service
    public readonly tokenUsersTable: Table;
    public readonly tokenCacheTable: Table;
    public readonly tokenHandler: IFunction;
    public readonly tokenApi: SpecRestApi;

    // Storage Service
    public readonly storageTable: Table;
    public readonly hawkAuthorizerHandler: IFunction;
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

        // Tables
        this.tokenUsersTable = this.buildTokenUsersTable();
        this.tokenCacheTable = this.buildTokenCacheTable();
        this.storageTable = this.buildStorageTable();

        // Handlers
        this.hawkAuthorizerHandler = this.buildHawkAuthorizerHandler();
        this.tokenHandler = this.buildTokenApiHandler();
        this.storageHandler = this.buildStorageApiHandler();

        // APIs
        this.tokenApi = this.buildApi(Service.TOKEN, this.tokenHandler);
        this.storageApi = this.buildApi(Service.STORAGE, this.storageHandler);
    }

    private buildStorageTable(): Table {
        const table = new Table(this, "StorageTable", {
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
            removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
        });

        // Add GSI for efficient user collection queries
        table.addGlobalSecondaryIndex({
            indexName: "UserCollectionsIndex",
            partitionKey: {
                name: "user_id",
                type: AttributeType.STRING,
            },
            sortKey: {
                name: "name",
                type: AttributeType.STRING,
            },
            projectionType: ProjectionType.ALL,
        });

        return table;
    }

    private buildTokenUsersTable(): Table {
        return new Table(this, "TokenUsersTable", {
            tableName: `ffsync-token-users-${this.props.stageType.toLowerCase()}`,
            encryption: TableEncryption.AWS_MANAGED,
            partitionKey: {
                name: "PK",
                type: AttributeType.STRING,
            },
            billingMode: BillingMode.PAY_PER_REQUEST,
            pointInTimeRecoverySpecification: {
                pointInTimeRecoveryEnabled: true,
            },
            removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
        });
    }

    private buildTokenCacheTable(): Table {
        const table = new Table(this, "TokenCacheTable", {
            tableName: `ffsync-token-cache-${this.props.stageType.toLowerCase()}`,
            encryption: TableEncryption.AWS_MANAGED,
            partitionKey: {
                name: "PK",
                type: AttributeType.STRING,
            },
            billingMode: BillingMode.PAY_PER_REQUEST,
            timeToLiveAttribute: "expiry",
            pointInTimeRecoverySpecification: {
                pointInTimeRecoveryEnabled: true,
            },
            removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
        });

        return table;
    }

    private buildHawkAuthorizerHandler(): PythonFunction {
        const fn = new PythonFunction(this, "HawkAuthorizerHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/__init__.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "hawk_authorizer_handler",
            functionName: `ffsync-hawk-authorizer-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(5),
            memorySize: 256,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
                TOKEN_CACHE_TABLE_NAME: this.tokenCacheTable.tableName,
                HAWK_TIMESTAMP_SKEW_TOLERANCE: "60",
                TOKEN_DURATION: "300",
            },
        });

        // Grant read permissions to token cache table
        this.tokenCacheTable.grantReadData(fn);
        fn.grantInvoke(this.apiExecuteRole);

        return fn;
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
                BASE_DOMAIN: this.stageBaseDomain,
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
        const oidcSecret = new Secret(this, "OidcSecret", {
            secretName: `ffsync-oidc-config-${this.props.stageType.toLowerCase()}`,
            description: "OIDC provider configuration for Token Server",
        });

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
                BASE_DOMAIN: this.stageBaseDomain,
                OIDC_SECRET_ARN: oidcSecret.secretArn,
                TOKEN_USERS_TABLE_NAME: this.tokenUsersTable.tableName,
                TOKEN_CACHE_TABLE_NAME: this.tokenCacheTable.tableName,
                CLOCK_SKEW_TOLERANCE: "300",
                OIDC_CACHE_TTL_SECONDS: "3600",
                HAWK_TIMESTAMP_SKEW_TOLERANCE: "60",
                RETRY_AFTER_SECONDS: "30",
                TOKEN_DURATION: "300",
            },
        });

        // Grant permissions
        oidcSecret.grantRead(fn);
        this.tokenUsersTable.grantReadWriteData(fn);
        this.tokenCacheTable.grantReadWriteData(fn);
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
        const apiName = `ffsync-${service.toLowerCase()}-${this.props.stageType}`;
        const logGroup = new LogGroup(this, `${capitalService}ApiGatewayAccessLogs`, {
            logGroupName: `${apiName}-api-access-logs`,
            retention: RetentionDays.ONE_MONTH,
        });
        const api = new SpecRestApi(this, `${capitalService}Api`, {
            apiDefinition: ApiDefinition.fromInline(openApiSpec),
            endpointTypes: [EndpointType.EDGE],
            restApiName: apiName,
            domainName: {
                domainName,
                certificate,
                securityPolicy: SecurityPolicy.TLS_1_2,
            },
            deployOptions: {
                stageName: this.props.stageType.toLowerCase(),
                metricsEnabled: true,
                loggingLevel: MethodLoggingLevel.INFO,
                accessLogDestination: new LogGroupLogDestination(logGroup),
                accessLogFormat: AccessLogFormat.jsonWithStandardFields(),
            },
            disableExecuteApiEndpoint: true,
        });
        api.node.addDependency(handler);
        if (service == Service.STORAGE) {
            api.node.addDependency(this.hawkAuthorizerHandler);
        }

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

        // Add HAWK authorizer to Storage API
        if (service === Service.STORAGE) {
            openApiJson = openApiJson.replace(
                /CDK_AUTH_LAMBDA_FUNCTION_ARN/g,
                this.hawkAuthorizerHandler.functionArn,
            );
        }
        return JSON.parse(openApiJson);
    }
}
