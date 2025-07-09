import {Construct} from "constructs";

import {SecretValue, Stack, StackProps, Stage, StageProps} from "aws-cdk-lib";
import {PipelineType} from "aws-cdk-lib/aws-codepipeline";
import * as pipelines from "aws-cdk-lib/pipelines";

import {ACCOUNT_ID, REGION, StageType} from "../config";
import {ServiceStack} from "./service";

export class PipelineStack extends Stack {
    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        const pipeline = new pipelines.CodePipeline(this, "Pipeline", {
            pipelineType: PipelineType.V2,
            synth: new pipelines.ShellStep("Synth", {
                input: pipelines.CodePipelineSource.gitHub("layertwo/ffsync", "mainline", {
                    authentication: SecretValue.secretsManager("ffsync-github-cdk"),
                }),
                commands: ["npm ci", "npm run build", "npx cdk synth"],
            }),
            selfMutation: true,
        });

        pipeline.addStage(
            new LogicalStage(this, "Beta", {
                env: {
                    account: ACCOUNT_ID,
                    region: REGION,
                },
                stageType: StageType.BETA,
            }),
        );

        pipeline.addStage(
            new LogicalStage(this, "Prod", {
                env: {
                    account: ACCOUNT_ID,
                    region: REGION,
                },
                stageType: StageType.PROD,
            }),
        );
    }
}

export interface LogicalStageProps extends StageProps {
    stageType: StageType;
}

export class LogicalStage extends Stage {
    constructor(scope: Construct, id: string, props: LogicalStageProps) {
        super(scope, id, props);

        new ServiceStack(this, `ServiceStack`, {
            env: props.env,
            stageType: props.stageType,
        });
    }
}
