#!/usr/bin/env node
import {App} from "aws-cdk-lib";

import {ACCOUNT_ID, REGION, StageType} from "./config";
import {FrontendStack} from "./stacks/frontend";
import {GitHubOidcStack} from "./stacks/github-oidc";
import {MonitoringStack} from "./stacks/monitoring";
import {ServiceStack} from "./stacks/service";

const app = new App();

const env = {account: ACCOUNT_ID, region: REGION};

new GitHubOidcStack(app, "GitHubOidcStack", {
    env,
    githubOrg: "layertwo",
    githubRepo: "ffsync",
});

[StageType.PROD].forEach((stageType) => {
    const serviceStack = new ServiceStack(app, `Service-${stageType.toLowerCase()}`, {
        env,
        stageType,
    });

    new MonitoringStack(app, `Monitoring-${stageType.toLowerCase()}`, {
        env,
        stageType,
        storageApi: serviceStack.storageApi,
        storageHandler: serviceStack.storageHandler,
        storageTable: serviceStack.storageTable,
    });

    new FrontendStack(app, `Frontend-${stageType.toLowerCase()}`, {
        env,
        stageType,
        tokenApiDomain: serviceStack.tokenApiDomain,
        oidcProviderUrl: serviceStack.oidcProviderUrlParam,
        clientId: serviceStack.clientIdParam,
    });
});

app.synth();
