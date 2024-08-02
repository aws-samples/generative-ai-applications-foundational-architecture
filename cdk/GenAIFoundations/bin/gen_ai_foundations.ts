import 'source-map-support/register';
import * as cdk from 'aws-cdk-lib';
import { GenAIFoundationsStack } from '../lib/foundations-main-stack';
import { WafStack } from '../lib/waf-stack';
import * as crypto from "crypto";

const app = new cdk.App();
const uniqueCode = crypto.randomBytes(8).toString("hex").slice(0, 5);

const wafStack = new WafStack(app, 'WafStack'+uniqueCode, {
    env: { region: 'us-east-1' },
    crossRegionReferences:true
  });

new GenAIFoundationsStack(app, 'GenAIFoundations'+uniqueCode, {
    env: {
        region: process.env.CDK_DEFAULT_REGION
    },
    crossRegionReferences:true,
    webAclArn: wafStack.webAclArn
});