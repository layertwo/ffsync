import { SecretValue, Stack, StackProps, Stage, StageProps } from "aws-cdk-lib";
import * as pipelines from "aws-cdk-lib/pipelines";
import { Construct } from "constructs";
import { ServiceStack } from "./service";
import { PipelineType } from "aws-cdk-lib/aws-codepipeline";

export class PipelineStack extends Stack {

    constructor(scope: Construct, id: string, props?: StackProps) {
        super(scope, id, props);

        const pipeline = new pipelines.CodePipeline(this, 'Pipeline', {
        pipelineType: PipelineType.V2,
        synth: new pipelines.ShellStep('Synth', {
            input: pipelines.CodePipelineSource.gitHub('layertwo/ffsync', 'mainline', {
                authentication: SecretValue.secretsManager("ffsync-github-cdk"),
            }),
            commands: [
            'npm ci',
            'npm run build',
            'npx cdk synth',
            ],
        }),
        selfMutation: true,
        });

        pipeline.addStage(new LogicalStage(this, 'Beta', {
            env: { 
                account: props?.env?.account, 
                region: 'us-west-2'
            }, 
            stageName: "beta" 
        }));
        pipeline.addStage(new LogicalStage(this, 'Prod', {
            env: { 
                account: props?.env?.account, 
                region: 'us-west-2'
            }, 
            stageName: "prod" 
        }));
  }
}

export interface LogicalStageProps extends StageProps {
    stageName: string;
}

export class LogicalStage extends Stage {
  constructor(scope: Construct, id: string, props: LogicalStageProps) {
    super(scope, id, props);

    const serviceStack = new ServiceStack(this, `ServiceStack`, { env: props.env, stage: props.stageName })
  }
}
