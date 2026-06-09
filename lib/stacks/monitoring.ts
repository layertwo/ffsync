import {MonitoringFacade} from "cdk-monitoring-constructs";
import {Construct} from "constructs";

import {Duration, Stack, StackProps} from "aws-cdk-lib";
import {SpecRestApi} from "aws-cdk-lib/aws-apigateway";
import {Function as CfFunction, Distribution} from "aws-cdk-lib/aws-cloudfront";
import {Metric} from "aws-cdk-lib/aws-cloudwatch";
import {Table} from "aws-cdk-lib/aws-dynamodb";
import {IFunction} from "aws-cdk-lib/aws-lambda";

import {StageType} from "../config";

export interface MonitoringStackProps extends StackProps {
    stageType: StageType;
    authApi: SpecRestApi;
    authHandler: IFunction;
    authTable: Table;
    tokenApi: SpecRestApi;
    tokenHandler: IFunction;
    tokenUsersTable: Table;
    tokenCacheTable: Table;
    profileApi: SpecRestApi;
    profileHandler: IFunction;
    storageApi: SpecRestApi;
    storageHandler: IFunction;
    storageTable: Table;
    distribution: Distribution;
    wellKnownFunction: CfFunction;
}

export class MonitoringStack extends Stack {
    private readonly props: MonitoringStackProps;
    private readonly monitoring: MonitoringFacade;

    constructor(scope: Construct, id: string, props: MonitoringStackProps) {
        super(scope, id, props);
        this.props = props;

        this.monitoring = new MonitoringFacade(this, `FFSync-${this.props.stageType}`, {});
        this.monitorAuth();
        this.monitorToken();
        this.monitorProfile();
        this.monitorStorage();
        this.monitorFrontend();
    }

    private monitorAuth(): void {
        const period = Duration.minutes(5);
        this.monitoring
            .addLargeHeader("Auth")
            .monitorApiGateway({
                api: this.props.authApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.authHandler,
            })
            .monitorDynamoTable({table: this.props.authTable})
            .monitorCustom({
                alarmFriendlyName: "Auth Business Outcomes",
                metricGroups: [
                    {
                        title: "Sessions Created",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "SessionsCreated",
                                statistic: "Sum",
                                period,
                                label: "Sessions Created",
                            }),
                        ],
                    },
                    {
                        title: "Access Tokens Issued",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "AccessTokensIssued",
                                statistic: "Sum",
                                period,
                                label: "Access Tokens Issued",
                            }),
                        ],
                    },
                    {
                        title: "Hawk Authentication",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "HawkAuthSuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "HawkAuthFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                ],
            })
            .monitorCustom({
                alarmFriendlyName: "OIDC Token Endpoint",
                metricGroups: [
                    {
                        title: "Token Endpoint Outcome (POST /api/oidc/token)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCTokenSuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCTokenFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                    {
                        title: "Token Endpoint Latency (ms)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCTokenLatencyMs",
                                statistic: "p50",
                                period,
                                label: "p50",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCTokenLatencyMs",
                                statistic: "p99",
                                period,
                                label: "p99",
                            }),
                        ],
                    },
                ],
            })
            .monitorCustom({
                alarmFriendlyName: "OIDC JWKS Endpoint",
                metricGroups: [
                    {
                        title: "JWKS Outcome (GET /.well-known/jwks.json)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCJWKSSuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCJWKSFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                    {
                        title: "JWKS Latency (ms)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCJWKSLatencyMs",
                                statistic: "p50",
                                period,
                                label: "p50",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCJWKSLatencyMs",
                                statistic: "p99",
                                period,
                                label: "p99",
                            }),
                        ],
                    },
                ],
            })
            .monitorCustom({
                alarmFriendlyName: "OIDC Discovery",
                metricGroups: [
                    {
                        title: "Discovery Outcome (GET /.well-known/openid-configuration)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCDiscoverySuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCDiscoveryFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                    {
                        title: "Discovery Latency (ms)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCDiscoveryLatencyMs",
                                statistic: "p50",
                                period,
                                label: "p50",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCDiscoveryLatencyMs",
                                statistic: "p99",
                                period,
                                label: "p99",
                            }),
                        ],
                    },
                ],
            })
            .monitorCustom({
                alarmFriendlyName: "OIDC Userinfo",
                metricGroups: [
                    {
                        title: "Userinfo Outcome (GET /api/oidc/userinfo)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCUserinfoSuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCUserinfoFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                    {
                        title: "Userinfo Latency (ms)",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCUserinfoLatencyMs",
                                statistic: "p50",
                                period,
                                label: "p50",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "OIDCUserinfoLatencyMs",
                                statistic: "p99",
                                period,
                                label: "p99",
                            }),
                        ],
                    },
                ],
            });
    }

    private monitorToken(): void {
        const period = Duration.minutes(5);
        this.monitoring
            .addLargeHeader("Token")
            .monitorApiGateway({
                api: this.props.tokenApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.tokenHandler,
            })
            .monitorDynamoTable({table: this.props.tokenUsersTable})
            .monitorDynamoTable({table: this.props.tokenCacheTable})
            .monitorCustom({
                alarmFriendlyName: "Token Business Outcomes",
                metricGroups: [
                    {
                        title: "Sync Tokens Issued",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "SyncTokensIssued",
                                statistic: "Sum",
                                period,
                                label: "Sync Tokens Issued",
                            }),
                        ],
                    },
                ],
            });
    }

    private monitorProfile(): void {
        const period = Duration.minutes(5);
        this.monitoring
            .addLargeHeader("Profile")
            .monitorApiGateway({
                api: this.props.profileApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.profileHandler,
            })
            .monitorCustom({
                alarmFriendlyName: "Profile Authentication",
                metricGroups: [
                    {
                        title: "JWT Bearer Authentication",
                        metrics: [
                            new Metric({
                                namespace: "ffsync",
                                metricName: "JWTAuthSuccess",
                                statistic: "Sum",
                                period,
                                label: "Success",
                            }),
                            new Metric({
                                namespace: "ffsync",
                                metricName: "JWTAuthFailure",
                                statistic: "Sum",
                                period,
                                label: "Failure",
                            }),
                        ],
                    },
                ],
            });
    }

    private monitorStorage(): void {
        this.monitoring
            .addLargeHeader("Storage")
            .monitorApiGateway({
                api: this.props.storageApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.storageHandler,
            })
            .monitorDynamoTable({table: this.props.storageTable});
    }

    private monitorFrontend(): void {
        const functionName = this.props.wellKnownFunction.functionName;
        const cfFunctionDimensions = {FunctionName: functionName};

        this.monitoring
            .addLargeHeader("Frontend")
            .monitorCloudFrontDistribution({
                distribution: this.props.distribution,
            })
            .monitorCustom({
                alarmFriendlyName: "CloudFront Function",
                metricGroups: [
                    {
                        title: "CloudFront Function - Invocations & Errors",
                        metrics: [
                            new Metric({
                                namespace: "AWS/CloudFront",
                                metricName: "FunctionInvocations",
                                dimensionsMap: cfFunctionDimensions,
                                statistic: "Sum",
                                period: Duration.minutes(5),
                                label: "Invocations",
                            }),
                            new Metric({
                                namespace: "AWS/CloudFront",
                                metricName: "FunctionValidationErrors",
                                dimensionsMap: cfFunctionDimensions,
                                statistic: "Sum",
                                period: Duration.minutes(5),
                                label: "Validation Errors",
                            }),
                            new Metric({
                                namespace: "AWS/CloudFront",
                                metricName: "FunctionExecutionErrors",
                                dimensionsMap: cfFunctionDimensions,
                                statistic: "Sum",
                                period: Duration.minutes(5),
                                label: "Execution Errors",
                            }),
                        ],
                    },
                    {
                        title: "CloudFront Function - Compute Utilization",
                        metrics: [
                            new Metric({
                                namespace: "AWS/CloudFront",
                                metricName: "FunctionComputeUtilization",
                                dimensionsMap: cfFunctionDimensions,
                                statistic: "Average",
                                period: Duration.minutes(5),
                                label: "Compute Utilization",
                            }),
                        ],
                    },
                ],
            });
    }
}
