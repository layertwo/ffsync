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

    const frontendStack = new FrontendStack(app, `Frontend-${stageType.toLowerCase()}`, {
        env,
        stageType,
        authApiDomain: serviceStack.authApiDomain,
        tokenApiDomain: serviceStack.tokenApiDomain,
        profileApiDomain: serviceStack.profileApiDomain,
        oidcProviderUrl: serviceStack.oidcProviderUrlParam,
        clientId: serviceStack.clientIdParam,
    });

    new MonitoringStack(app, `Monitoring-${stageType.toLowerCase()}`, {
        env,
        stageType,
        authApi: serviceStack.authApi,
        authHandler: serviceStack.authHandler,
        authTable: serviceStack.authTable,
        tokenApi: serviceStack.tokenApi,
        tokenHandler: serviceStack.tokenHandler,
        tokenUsersTable: serviceStack.tokenUsersTable,
        tokenCacheTable: serviceStack.tokenCacheTable,
        profileApi: serviceStack.profileApi,
        profileHandler: serviceStack.profileHandler,
        storageApi: serviceStack.storageApi,
        storageHandler: serviceStack.storageHandler,
        storageTable: serviceStack.storageTable,
        distribution: frontendStack.distribution,
        wellKnownFunction: frontendStack.wellKnownFunction,
    });
});

app.synth();
