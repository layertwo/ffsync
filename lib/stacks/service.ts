import {PythonFunction} from "uv-python-lambda";
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
import {Key, KeySpec, KeyUsage} from "aws-cdk-lib/aws-kms";
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
import {IStringParameter, StringParameter} from "aws-cdk-lib/aws-ssm";

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

    public readonly oidcProviderUrlParam: IStringParameter;
    public readonly clientIdParam: IStringParameter;

    private get stageBaseDomain(): string {
        return `${this.props.stageType.toLowerCase()}.${BASE_DOMAIN}`;
    }

    public get authApiDomain(): string {
        return `${Service.AUTH}.${this.props.stageType}.${BASE_DOMAIN}`;
    }

    public get tokenApiDomain(): string {
        return `${Service.TOKEN}.${this.props.stageType}.${BASE_DOMAIN}`;
    }

    public get profileApiDomain(): string {
        return `${Service.PROFILE}.${this.props.stageType}.${BASE_DOMAIN}`;
    }

    // Auth Service
    public readonly tokenUsersTable: Table;
    public readonly tokenCacheTable: Table;
    public readonly authTable: Table;
    public readonly signingKey: Key;
    public readonly authHandler: IFunction;
    public readonly authApi: SpecRestApi;

    // Token Service
    public readonly tokenHandler: IFunction;
    public readonly tokenApi: SpecRestApi;

    // Profile Service
    public readonly profileHandler: IFunction;
    public readonly profileApi: SpecRestApi;

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

        this.oidcProviderUrlParam = StringParameter.fromStringParameterName(
            this, "OidcProviderUrl", `/ffsync/${props.stageType.toLowerCase()}/oidc-provider-url`,
        );
        this.clientIdParam = StringParameter.fromStringParameterName(
            this, "ClientId", `/ffsync/${props.stageType.toLowerCase()}/client-id`,
        );

        // Tables
        this.tokenUsersTable = this.buildTokenUsersTable();
        this.tokenCacheTable = this.buildTokenCacheTable();
        this.authTable = this.buildAuthTable();
        this.storageTable = this.buildStorageTable();

        // KMS
        this.signingKey = this.buildSigningKey();

        // Handlers
        this.hawkAuthorizerHandler = this.buildHawkAuthorizerHandler();
        this.authHandler = this.buildAuthApiHandler();
        this.tokenHandler = this.buildTokenApiHandler();
        this.profileHandler = this.buildProfileApiHandler();
        this.storageHandler = this.buildStorageApiHandler();

        // APIs
        this.authApi = this.buildApi(Service.AUTH, this.authHandler);
        this.tokenApi = this.buildApi(Service.TOKEN, this.tokenHandler);
        this.profileApi = this.buildApi(Service.PROFILE, this.profileHandler);
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

    private buildAuthTable(): Table {
        return new Table(this, "AuthTable", {
            tableName: `ffsync-auth-${this.props.stageType.toLowerCase()}`,
            partitionKey: {name: "PK", type: AttributeType.STRING},
            billingMode: BillingMode.PAY_PER_REQUEST,
            encryption: TableEncryption.AWS_MANAGED,
            timeToLiveAttribute: "expiry",
            pointInTimeRecoverySpecification: {
                pointInTimeRecoveryEnabled: true,
            },
            removalPolicy: RemovalPolicy.RETAIN_ON_UPDATE_OR_DELETE,
        });
    }

    private buildSigningKey(): Key {
        return new Key(this, "AuthSigningKey", {
            alias: `ffsync-auth-signing-${this.props.stageType.toLowerCase()}`,
            keySpec: KeySpec.RSA_2048,
            keyUsage: KeyUsage.SIGN_VERIFY,
            description: "Signs OAuth JWTs for the FxA auth server",
        });
    }

    private buildHawkAuthorizerHandler(): PythonFunction {
        const fn = new PythonFunction(this, "HawkAuthorizerHandler", {
            rootDir: path.join(__dirname, "../../lambda"),
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
            bundling: {
                assetExcludes: [".venv/", ".git/", "tests/", "htmlcov/", ".pytest_cache/", ".mypy_cache/"],
            },
        });

        // Grant read/write permissions to token cache table (read for credential
        // lookup, write for nonce replay protection)
        this.tokenCacheTable.grantReadWriteData(fn);
        fn.grantInvoke(this.apiExecuteRole);

        return fn;
    }

    private buildStorageApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "ApiHandler", {
            rootDir: path.join(__dirname, "../../lambda"),
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
            bundling: {
                assetExcludes: [".venv/", ".git/", "tests/", "htmlcov/", ".pytest_cache/", ".mypy_cache/"],
            },
        });

        // Grant DynamoDB permissions to Lambda
        this.storageTable.grantReadWriteData(fn);
        fn.grantInvoke(this.apiExecuteRole);
        this.exportValue(fn.functionName);

        return fn;
    }

    private buildAuthApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "AuthApiHandler", {
            rootDir: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/__init__.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "auth_api_handler",
            functionName: `ffsync-auth-api-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            memorySize: 512,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
                BASE_DOMAIN: this.stageBaseDomain,
                OIDC_PROVIDER_URL: this.oidcProviderUrlParam.stringValue,
                OIDC_CLIENT_ID: this.clientIdParam.stringValue,
                AUTH_TABLE_NAME: this.authTable.tableName,
                AUTH_SIGNING_KEY_ID: this.signingKey.keyId,
                CLOCK_SKEW_TOLERANCE: "300",
                OIDC_CACHE_TTL_SECONDS: "3600",
                HAWK_TIMESTAMP_SKEW_TOLERANCE: "60",
            },
        });

        // Grant permissions
        this.authTable.grantReadWriteData(fn);
        this.signingKey.grantSign(fn);
        this.signingKey.grant(fn, "kms:GetPublicKey");
        fn.grantInvoke(this.apiExecuteRole);

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
                BASE_DOMAIN: this.stageBaseDomain,
                TOKEN_USERS_TABLE_NAME: this.tokenUsersTable.tableName,
                TOKEN_CACHE_TABLE_NAME: this.tokenCacheTable.tableName,
                AUTH_SIGNING_KEY_ID: this.signingKey.keyId,
                HAWK_TIMESTAMP_SKEW_TOLERANCE: "60",
                TOKEN_DURATION: "300",
                RETRY_AFTER_SECONDS: "30",
            },
            bundling: {
                assetExcludes: [".venv/", ".git/", "tests/", "htmlcov/", ".pytest_cache/", ".mypy_cache/"],
            },
        });

        // Grant permissions
        this.tokenUsersTable.grantReadWriteData(fn);
        this.tokenCacheTable.grantReadWriteData(fn);
        this.signingKey.grant(fn, "kms:GetPublicKey");
        fn.grantInvoke(this.apiExecuteRole);

        return fn;
    }

    private buildProfileApiHandler(): PythonFunction {
        const fn = new PythonFunction(this, "ProfileApiHandler", {
            entry: path.join(__dirname, "../../lambda"),
            index: "src/entrypoint/__init__.py",
            runtime: Runtime.PYTHON_3_14,
            architecture: Architecture.ARM_64,
            handler: "profile_api_handler",
            functionName: `ffsync-profile-api-${this.props.stageType.toLowerCase()}`,
            timeout: Duration.seconds(29),
            memorySize: 512,
            environment: {
                STAGE: this.props.stageType.toLowerCase(),
                BASE_DOMAIN: this.stageBaseDomain,
                AUTH_TABLE_NAME: this.authTable.tableName,
                AUTH_SIGNING_KEY_ID: this.signingKey.keyId,
            },
        });

        // Grant permissions (read-only for auth table)
        this.authTable.grantReadData(fn);
        this.signingKey.grant(fn, "kms:GetPublicKey");
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
        openApiJson = openApiJson.replace(
            /CDK_CORS_ORIGIN/g, `https://${this.stageBaseDomain}`,
        );

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
