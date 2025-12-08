import {MonitoringFacade} from "cdk-monitoring-constructs";
import {Construct} from "constructs";

import {Stack, StackProps} from "aws-cdk-lib";
import {SpecRestApi} from "aws-cdk-lib/aws-apigateway";
import {Table} from "aws-cdk-lib/aws-dynamodb";
import {IFunction} from "aws-cdk-lib/aws-lambda";

import {StageType} from "../config";

export interface MonitoringStackProps extends StackProps {
    stageType: StageType;
    storageApi: SpecRestApi;
    storageHandler: IFunction;
    storageTable: Table;
}

export class MonitoringStack extends Stack {
    private readonly props: MonitoringStackProps;
    private readonly monitoring: MonitoringFacade;

    constructor(scope: Construct, id: string, props: MonitoringStackProps) {
        super(scope, id, props);
        this.props = props;

        this.monitoring = new MonitoringFacade(this, `FFSync-${this.props.stageType}`, {});
        this.monitorApi();
        this.monitorStorage();
    }

    private monitorApi(): void {
        this.monitoring
            .addLargeHeader("API")
            .monitorApiGateway({
                api: this.props.storageApi,
                apiStage: this.props.stageType.toLowerCase(),
            })
            .monitorLambdaFunction({
                lambdaFunction: this.props.storageHandler,
            });
    }

    private monitorStorage(): void {
        this.monitoring
            .addLargeHeader("Storage")
            .monitorDynamoTable({table: this.props.storageTable});
    }
}
