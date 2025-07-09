#!/usr/bin/env node
import {App} from "aws-cdk-lib";

import {ACCOUNT_ID, REGION} from "./config";
import {PipelineStack} from "./stacks/pipeline";

const app = new App();

new PipelineStack(app, "Pipeline", {env: {account: ACCOUNT_ID, region: REGION}});

app.synth();
