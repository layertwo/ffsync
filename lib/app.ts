#!/usr/bin/env node
import { App } from 'aws-cdk-lib';

import { PipelineStack } from './stacks/pipeline';
import { ACCOUNT_ID } from './config';

const app = new App()

new PipelineStack(app, "Pipeline", {env: {account: ACCOUNT_ID, region: "us-west-2"}});

app.synth();