import * as cdk from "aws-cdk-lib";
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import * as s3 from "aws-cdk-lib/aws-s3";
import { Construct } from "constructs";
import * as crypto from "crypto";



// Stack to create the WAF WebACL in us-east-1
export class WafStack extends cdk.Stack {
  public readonly webAclArn: string;

  constructor(scope: Construct, id: string, props?: cdk.StackProps) {
    super(scope, id, {
      ...props,
      env: { region: 'us-east-1' },
    });

    const userEmail = new cdk.CfnParameter(this, "userEmail", {
        type: "String",
        description: "Email address for the admin portal user. Temporary password will be sent to this email address.",
      });

    // Create the WAF WebACL

    const uniqueCode = crypto.randomBytes(8).toString("hex").slice(0, 5);

    const webAcl = new wafv2.CfnWebACL(this, 'FoundationsWebACL'+uniqueCode, {
        defaultAction: {
          allow: {},
        },
        scope: 'CLOUDFRONT',
        visibilityConfig: {
          cloudWatchMetricsEnabled: true,
          metricName: 'foundations-web-acl'+uniqueCode,
          sampledRequestsEnabled: true,
        },
        rules: [
          {
            name: 'AWS-AWSManagedRulesCommonRuleSet',
            priority: 0,
            overrideAction: { none: {} },
            statement: {
              managedRuleGroupStatement: {
                vendorName: 'AWS',
                name: 'AWSManagedRulesCommonRuleSet',
              },
            },
            visibilityConfig: {
              cloudWatchMetricsEnabled: true,
              metricName: 'AWSManagedRulesCommonRuleSet',
              sampledRequestsEnabled: true,
            },
          },
        ],
      });
    this.webAclArn = webAcl.attrArn;
  }
}