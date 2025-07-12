import {Construct} from "constructs";

import {SecretValue, Stack, StackProps, Stage, StageProps} from "aws-cdk-lib";
import {ComputeType, LinuxArmBuildImage} from "aws-cdk-lib/aws-codebuild";
import {PipelineType} from "aws-cdk-lib/aws-codepipeline";
import * as pipelines from "aws-cdk-lib/pipelines";

import {ACCOUNT_ID, REGION, SMITHY_DOWNLOAD_URL, StageType} from "../config";
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
                installCommands: [
                    "mkdir -p smithy-install/smithy",
                    `curl -L ${SMITHY_DOWNLOAD_URL} -o smithy-install/smithy-cli-linux-aarch64.zip`,
                    "unzip -qo smithy-install/smithy-cli-linux-aarch64.zip -d smithy-install",
                    "mv smithy-install/smithy-cli-linux-aarch64/* smithy-install/smithy",
                    "sudo smithy-install/smithy/install",
                ],
                commands: [
                    "npm ci",
                    "npx smithy build -c smithy/smithy-build.json smithy",
                    "npm run build",
                    "npx cdk synth",
                ],
                primaryOutputDirectory: "build/cdk.out",
            }),
            selfMutation: true,
            codeBuildDefaults: {
                buildEnvironment: {
                    buildImage: LinuxArmBuildImage.AMAZON_LINUX_2_STANDARD_3_0,
                    computeType: ComputeType.SMALL,
                },
            },
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
