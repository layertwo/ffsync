import {MonitoringFacade} from "cdk-monitoring-constructs";
import {Construct} from "constructs";

import {Duration, Stack, StackProps} from "aws-cdk-lib";
import {SpecRestApi} from "aws-cdk-lib/aws-apigateway";
import {Distribution, Function as CfFunction} from "aws-cdk-lib/aws-cloudfront";
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
        this.monitoring
            .addLargeHeader("Auth")
            .monitorApiGateway({
                api: this.props.authApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.authHandler,
            })
            .monitorDynamoTable({table: this.props.authTable});
    }

    private monitorToken(): void {
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
            .monitorDynamoTable({table: this.props.tokenCacheTable});
    }

    private monitorProfile(): void {
        this.monitoring
            .addLargeHeader("Profile")
            .monitorApiGateway({
                api: this.props.profileApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.profileHandler,
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
