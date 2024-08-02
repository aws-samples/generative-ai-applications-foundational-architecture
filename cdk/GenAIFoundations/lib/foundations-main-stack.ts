import * as cdk from "aws-cdk-lib";
import { Construct } from "constructs";
import * as ec2 from "aws-cdk-lib/aws-ec2";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as ecs from "aws-cdk-lib/aws-ecs";
import * as elbv2 from "aws-cdk-lib/aws-elasticloadbalancingv2";
import * as targets from "aws-cdk-lib/aws-elasticloadbalancingv2-targets";
import * as iam from "aws-cdk-lib/aws-iam";
import * as cognito from "aws-cdk-lib/aws-cognito";
import * as apigwrestapi from "aws-cdk-lib/aws-apigateway";
import { Aws } from "aws-cdk-lib/core";
import * as dynamodb from "aws-cdk-lib/aws-dynamodb";
import * as crypto from "crypto";
import * as sqs from "aws-cdk-lib/aws-sqs";
import * as logs from 'aws-cdk-lib/aws-logs';
import * as kms from 'aws-cdk-lib/aws-kms';
import { CfnOutput, Duration, RemovalPolicy } from 'aws-cdk-lib';
import * as cloudfront_origins from 'aws-cdk-lib/aws-cloudfront-origins';
import * as cloudfront from 'aws-cdk-lib/aws-cloudfront';
import { aws_opensearchserverless as opensearchserverless } from 'aws-cdk-lib';
import { aws_elasticache as elasticache } from 'aws-cdk-lib';
import { log } from "console";
import * as wafv2 from 'aws-cdk-lib/aws-wafv2';

interface SharedProps extends cdk.StackProps {
  webAclArn: string;
}

export class GenAIFoundationsStack extends cdk.Stack {
  constructor(scope: Construct, id: string, props: SharedProps) {
    super(scope, id, props);

    const userEmail = new cdk.CfnParameter(this, "userEmail", {
      type: "String",
      description: "Email address for the admin portal user. Temporary password will be sent to this email address.",
    });

    const uniqueCode = crypto.randomBytes(8).toString("hex").slice(0, 5);


    // Create an S3 bucket to store access logs
    const logBucket = new s3.Bucket(this, 'FoundationsAccessLog'+uniqueCode, {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryption: s3.BucketEncryption.S3_MANAGED,
      accessControl: s3.BucketAccessControl.LOG_DELIVERY_WRITE,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

   //create a KMS key
   const kmsKey = new kms.Key(this, 'FoundationsKmsKey'+uniqueCode, {
    enableKeyRotation: true,
    keyUsage: kms.KeyUsage.ENCRYPT_DECRYPT,
    removalPolicy: cdk.RemovalPolicy.DESTROY,
    policy: new iam.PolicyDocument({
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "kms:Encrypt",
            "kms:Decrypt",
            "kms:ReEncrypt*",
            "kms:GenerateDataKey*",
            "kms:DescribeKey",
          ],
          principals: [
            new iam.ServicePrincipal('logs.amazonaws.com'),
            new iam.ServicePrincipal('s3.amazonaws.com'),
            new iam.ServicePrincipal('apigateway.amazonaws.com'),
            new iam.ServicePrincipal('sqs.amazonaws.com'),
            new iam.ServicePrincipal('ecs-tasks.amazonaws.com')
          ],
          resources: ["*"],
        }),

        // root user
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "kms:*"
          ],
          principals: [
            new iam.AccountRootPrincipal()
          ],
          resources: ["*"],
        }),
      ],
    }),
  });
 


    // VPC for the ECS cluster
    const vpc = new ec2.Vpc(this, "FoundationsVPC"+uniqueCode, {
      ipAddresses: ec2.IpAddresses.cidr(this.node.tryGetContext("VPC_CIDR")),
      enableDnsSupport: true,
      enableDnsHostnames: true,
      maxAzs: 2,
      subnetConfiguration: [
        {
          cidrMask: 24,
          name: "PrivateSubnet",
          subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS
        },
        {
          cidrMask: 24,
          name: "IsolatedSubnet",
          subnetType: ec2.SubnetType.PUBLIC,
          mapPublicIpOnLaunch: false
        }
      ],
      vpcName: "FoundationsVPC"+uniqueCode,
    });

    // Create a CloudWatch Logs log group
    const flowLogsLogGroup = new logs.LogGroup(this, 'FoundationsVPCFlowLogsgroup'+uniqueCode, {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    // Create an IAM Role for VPC Flow Logs
    const flowLogRole = new iam.Role(this, 'FoundationsFlowLogRole'+uniqueCode, {
      assumedBy: new iam.ServicePrincipal('vpc-flow-logs.amazonaws.com'),
      managedPolicies: [
        iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonAPIGatewayPushToCloudWatchLogs')
      ]
    });

    // Create a Flow Log for the VPC
    new ec2.FlowLog(this, 'FoundationsVpcFlowLog'+uniqueCode, {
      resourceType: ec2.FlowLogResourceType.fromVpc(vpc),
      trafficType: ec2.FlowLogTrafficType.ALL,
      destination: ec2.FlowLogDestination.toCloudWatchLogs(flowLogsLogGroup, flowLogRole)
    });
    


    // VPC Endpoints for all the services
    const ecr_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsECREndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.ECR,
      privateDnsEnabled: true,
    })
    const ecr_docker_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsECRDockerEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.ECR_DOCKER,
      privateDnsEnabled: true,
    })

    const s3_endpoint = new ec2.GatewayVpcEndpoint(this, 'FoundationsS3GatewayEndpoint'+uniqueCode, {
      service: ec2.GatewayVpcEndpointAwsService.S3,
      vpc,
    })

    const cw_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsCWLogsEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.CLOUDWATCH_LOGS,
      privateDnsEnabled: true,
    })

    const sqs_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsSQSEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.SQS,
      privateDnsEnabled: true,
    })

    const dynamodb_endpoint = new ec2.GatewayVpcEndpoint(this, 'FoundationsDynamoDBEndpoint'+uniqueCode, {
      service: ec2.GatewayVpcEndpointAwsService.DYNAMODB,
      vpc
    })

    const textract_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsTextractEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.TEXTRACT,
      privateDnsEnabled: true
    })

    const bedrock_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsBedrockEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.BEDROCK,
      privateDnsEnabled: true
    })

    const bedrock_runtime_endpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsBedrockRuntimeEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
      privateDnsEnabled: true,
    })

    

    // Get the private subnets created by the VPC
    const privateSubnets = vpc.privateSubnets;

    // Create an ECS cluster in the private VPC
    const cluster = new ecs.Cluster(this, "FoundationsCluster"+uniqueCode, {
      vpc: vpc,
      clusterName: "FoundationsCluster"+uniqueCode,
    });

    // Cluster should be created after the VPC is available
    cluster.node.addDependency(vpc);

    // Create a Network Load Balancer and Application Load Balancer. Refer to the architecture diagram for details.
    const nlb = new elbv2.NetworkLoadBalancer(this, "FoundationsNLB"+uniqueCode, {
      vpc: vpc,
      vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
      internetFacing: false,
      deletionProtection: true
    });

        
    nlb.logAccessLogs(logBucket,'foundations-nlb-logs')

    const albtonlbsecurityGroup = new ec2.SecurityGroup(
      this,
      "FoundationsNLBtoALBSG"+uniqueCode,
      {
        vpc: vpc,
        allowAllOutbound: true,
      }
    );

    albtonlbsecurityGroup.connections.allowFrom(
      nlb.connections,
      ec2.Port.tcp(80),
      "Allow inbound traffic from the network load balancer"
    );

    const loadBalancer = new elbv2.ApplicationLoadBalancer(
      this,
      "FoundationsCluster" + "ALB"+uniqueCode,
      {
        vpc: vpc,
        vpcSubnets: { subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS },
        internetFacing: false,
        securityGroup: albtonlbsecurityGroup,
        deletionProtection: true
      }
    );


    loadBalancer.logAccessLogs(logBucket, 'foundations-alb-logs')

    // Create a target group for the ALB listener.

    const nlbTargetGroup = new elbv2.NetworkTargetGroup(this, "FoundationsNLBALBTG"+uniqueCode, {
      port: 80,
      vpc: vpc,
      targets: [new targets.AlbTarget(loadBalancer, 80)],
    });

    const nlbdefaultlistener = nlb.addListener("FoundationsNLBListener", {
      port: 80,
      defaultTargetGroups: [nlbTargetGroup],
    });

    // Path based routing for the ALB. Routes will be added later for the microservices.
    const listener = loadBalancer.addListener("FoundationsCluster-ALB-Listener", {
      port: 80,
    });

    listener.addAction("default", {
      action: elbv2.ListenerAction.fixedResponse(200, {
        contentType: "text/plain",
        messageBody: "Welcome to GenAI Foundations!",
      }),
    });

    const securityGroup = new ec2.SecurityGroup(
      this,
      "FoundationsFargateServiceSecurityGroup"+uniqueCode,
      {
        vpc: vpc,
        allowAllOutbound: true,
      }
    );
    securityGroup.connections.allowFrom(
      loadBalancer.connections,
      ec2.Port.tcp(80),
      "Allow inbound traffic from the load balancer"
    );
    securityGroup.connections.allowFrom(
      loadBalancer.connections,
      ec2.Port.tcp(443),
      "Allow inbound traffic from the load balancer"
    );

    const aossSecurityGroup = new ec2.SecurityGroup(
      this,
      "FoundationsAOSSSecurityGroup"+uniqueCode,
      {
        vpc: vpc,
        allowAllOutbound: true,
      }
    );

    aossSecurityGroup.connections.allowFrom(
      securityGroup,
      ec2.Port.tcp(80),
      "Allow inbound traffic from the load balancer"
    );

    aossSecurityGroup.connections.allowFrom(
      securityGroup,
      ec2.Port.tcp(443),
      "Allow inbound traffic from the load balancer"
    );

    // opensearchserverless vpc endpoint
    const aossEP = new opensearchserverless.CfnVpcEndpoint(this, 'foundationsaossendpoint', {
      name: 'foundationsaossendpoint',
      subnetIds: [vpc.privateSubnets[0].subnetId, vpc.privateSubnets[1].subnetId],
      vpcId: vpc.vpcId,
      securityGroupIds: [aossSecurityGroup.securityGroupId],
    });



    // const logGroup = new logs.LogGroup(this, "ApiGatewayAccessLogGroup", {
    //   removalPolicy: cdk.RemovalPolicy.DESTROY,
    //   encryptionKey: kmsKey,
    //   retention: logs.RetentionDays.THREE_MONTHS
    // });

    


    // // Create a REST API using API Gateway
    // const restApi = new apigwrestapi.RestApi(this, "FoundationsRestApi"+uniqueCode, {
    //   description: "This is the GenAI Foundations REST API",
    //   deployOptions: {
    //     accessLogDestination: new apigwrestapi.LogGroupLogDestination(logGroup),
    //     accessLogFormat: apigwrestapi.AccessLogFormat.jsonWithStandardFields(),
    //     },

    // });

    // Create an IAM role for API Gateway logging
const apiGatewayLogRole = new iam.Role(this, 'ApiGatewayLogRole', {
  assumedBy: new iam.ServicePrincipal('apigateway.amazonaws.com'),
  managedPolicies: [
    iam.ManagedPolicy.fromAwsManagedPolicyName('service-role/AmazonAPIGatewayPushToCloudWatchLogs')
  ],
});

// Create the CloudWatch LogGroup with encryption
const logGroup = new logs.LogGroup(this, 'ApiGatewayAccessLogGroup', {
  removalPolicy: cdk.RemovalPolicy.DESTROY,
  encryptionKey: kmsKey,
  retention: logs.RetentionDays.THREE_MONTHS,
});

// Create the API Gateway Rest API
const restApi = new apigwrestapi.RestApi(this, 'FoundationsRestApi', {
  description: 'This is the GenAI Foundations REST API',
  deployOptions: {
    accessLogDestination: new apigwrestapi.LogGroupLogDestination(logGroup),
    accessLogFormat: apigwrestapi.AccessLogFormat.jsonWithStandardFields(),
  },
});

restApi.addUsagePlan('FoundationsUsagePlan', {
  name: 'FoundationsUsagePlan',
  apiStages: [
    {
      api: restApi,
      stage: restApi.deploymentStage,
    },
  ],
  throttle: {
    rateLimit: 10000,
    burstLimit: 2000
  }
});

// Set the CloudWatch Logs role ARN in the API Gateway account settings
new apigwrestapi.CfnAccount(this, 'ApiGatewayAccount', {
  cloudWatchRoleArn: apiGatewayLogRole.roleArn,
});


    const restapiVpcLink = new apigwrestapi.VpcLink(
      this,
      "FoundationsVpcLink"+uniqueCode,
      {
        targets: [nlb],
      }
    );

    const resource = restApi.root.addResource("{proxy+}", {});

    // Integration with the NLB using VPC Link
    const integration_options = new apigwrestapi.Integration({
      type: apigwrestapi.IntegrationType.HTTP_PROXY,
      integrationHttpMethod: "ANY",
      uri: "http://" + nlb.loadBalancerDnsName + "/{proxy}",
      options: {
        connectionType: apigwrestapi.ConnectionType.VPC_LINK,
        vpcLink: restapiVpcLink,
        requestParameters: {
          "integration.request.path.proxy": "method.request.path.proxy",
        },
      },
    });

    // Cognito User Pool for authentication. This will be used by external applications to authenticate with the API.
    const cognitouserpool = new cognito.UserPool(this, "FoundationsAppsUserPool"+uniqueCode, {
      userPoolName: "FoundationsAppsUserPool"+uniqueCode,
    });

    cognitouserpool.addDomain("FoundationsAppsUserPoolDomain", {
      cognitoDomain: { domainPrefix: "foundationsuserpool"+uniqueCode },
    });

    const readOnlyScope = new cognito.ResourceServerScope({
      scopeName: "read",
      scopeDescription: "Read-only access",
    });

    const resourceServer = cognitouserpool.addResourceServer(
      "FoundationsAppsResourceServer",
      {
        userPoolResourceServerName: "apiendpoint",
        identifier: "genaifoundations",
        scopes: [readOnlyScope],
      }
    );
   
    // Cognito Authorizer for the API Gateway
    const auth = new apigwrestapi.CognitoUserPoolsAuthorizer(
      this,
      "FoundationsAuth",
      {
        cognitoUserPools: [cognitouserpool],
      }
    );

    resource.addMethod("ANY", integration_options, {
      authorizationType: apigwrestapi.AuthorizationType.COGNITO,
      authorizer: auth,
      authorizationScopes: ["genaifoundations/read"],
      requestParameters: {
        "method.request.path.proxy": true,
      },
    });


    /// Microservices

    const taskExecutionRole = new iam.Role(
      this,
      "FoundationsTaskExecutionRole"+uniqueCode,
      {
        assumedBy: new iam.ServicePrincipal("ecs-tasks.amazonaws.com")
      }
    );


     // Create a new IAM policy to allow access to required services, attach to above role
     const policy = new iam.ManagedPolicy(this, "FoundationsTaskExecutionPolicy"+uniqueCode, {
      statements: [
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: ["bedrock:InvokeModel"],
          resources: [
            "arn:aws:bedrock:*:"+Aws.ACCOUNT_ID+":provisioned-model/*",
            "arn:aws:bedrock:*::foundation-model/*"
          ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "bedrock:ListCustomModels",
            "bedrock:ListFoundationModels"
          ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions:  [
            "cognito-idp:DescribeUserPool",
            "cognito-idp:CreateUserPoolClient",
            "cognito-idp:DescribeUserPoolClient"
          ],
          resources: [
            "arn:aws:cognito-idp:*:"+Aws.ACCOUNT_ID+":userpool/*"
          ]
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "dynamodb:PutItem",
            "dynamodb:DeleteItem",
            "dynamodb:GetItem",
            "dynamodb:Scan",
            "dynamodb:Query",
            "dynamodb:UpdateItem"
        ],
          resources: ["arn:aws:dynamodb:*:"+Aws.ACCOUNT_ID+":table/foundations*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "dynamodb:Scan",
            "dynamodb:Query"
        ],
          resources: ["arn:aws:dynamodb:*:"+Aws.ACCOUNT_ID+":table/foundations*/index/*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "dynamodb:ListTables"
          ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "ecr:GetDownloadUrlForLayer",
            "ecr:BatchGetImage"
        ],
          resources: [
            "arn:aws:ecr:*:"+Aws.ACCOUNT_ID+":repository/admin_backend_service",
            "arn:aws:ecr:*:"+Aws.ACCOUNT_ID+":repository/foundations*"
        ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "ecr:GetAuthorizationToken"
          ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "aoss:CreateAccessPolicy",
            "aoss:CreateSecurityPolicy",
            "aoss:ListCollections",
            "aoss:TagResource",
            "aoss:CreateCollection"
        ],
          resources: ["*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "iam:CreateServiceLinkedRole",
            "aoss:DashboardsAccessAll",
            "aoss:APIAccessAll"
        ],
          resources: [
            "arn:aws:iam::"+Aws.ACCOUNT_ID+":role/aws-service-role/observability.aoss.amazonaws.com/AWSServiceRoleForAmazonOpenSearchServerless",
            "arn:aws:aoss:*:"+Aws.ACCOUNT_ID+":collection/*",
            "arn:aws:aoss:*:"+Aws.ACCOUNT_ID+":dashboards/default"
        ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "s3:PutObject",
            "s3:GetObject",
            "s3:ListBucket"
        ],
          resources: [
            "arn:aws:s3:::foundations*/*",
            "arn:aws:s3:::foundations*"
        ],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "secretsmanager:CreateSecret"
          ],
          resources: ["arn:aws:secretsmanager:*:"+Aws.ACCOUNT_ID+":secret:*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "sqs:DeleteMessage",
            "sqs:ChangeMessageVisibility",
            "sqs:ReceiveMessage",
            "sqs:SendMessage"
        ],
          resources: ["arn:aws:sqs:*:"+Aws.ACCOUNT_ID+":foundations*"],
        }),
        new iam.PolicyStatement({
          effect: iam.Effect.ALLOW,
          actions: [
            "textract:StartDocumentAnalysis",
            "textract:GetDocumentAnalysis"
        ],
          resources: ["*"],
        }),
      ],
      roles: [taskExecutionRole]
    });

    logGroup.grantWrite(taskExecutionRole);

    kmsKey.grantEncryptDecrypt(taskExecutionRole);

    
    // DynamoDB Table to store app_id and client_id mappings
    const app_clients_table = new dynamodb.TableV2(
      this,
      "AppClientsTable",
      {
        tableName: "foundations_appclients_"+uniqueCode,
        partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING }
      }
    );

    // Model Invocation Microservice

    // DynamoDB Table for Model Invocation Logging
    const modelInvocationLoggingTable = new dynamodb.TableV2(
      this,
      "ModelInvocationLoggingTable",
      {
        tableName: "foundations_llm_invocation_log_"+uniqueCode,
        partitionKey: { name: "invocation_id", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "timestamp", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "app_id_index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
          },
          {
            indexName: "model_id_index",
            partitionKey: { name: "model_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    // Redis cache security group
    const redisSecurityGroup = new ec2.SecurityGroup(
      this,
      "FoundationsRedisSecurityGroup"+uniqueCode,
      {
        vpc: vpc,
        allowAllOutbound: true,
      }
    );

    redisSecurityGroup.connections.allowFrom(
      securityGroup,
      ec2.Port.tcp(6379),
      "Allow inbound traffic from the ECS security group"
    );

    // Redis ElastiCache for async model invocation
    const serverless_redis = new elasticache.CfnServerlessCache(this, "FoundationsRedis"+uniqueCode, {
      engine: "redis",
      serverlessCacheName: "foundations-redis-"+uniqueCode,
      securityGroupIds: [redisSecurityGroup.securityGroupId],
      subnetIds: [vpc.privateSubnets[0].subnetId, vpc.privateSubnets[1].subnetId],
    });

    const elasticacheVpcEndpoint = new ec2.InterfaceVpcEndpoint(this, 'FoundationsElastiCacheEndpoint'+uniqueCode, {
      vpc,
      service: ec2.InterfaceVpcEndpointAwsService.ELASTICACHE,
      privateDnsEnabled: true,
    })

    const taskDefinition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsModelInvocationTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsModelInvocationTaskDef"+uniqueCode,
      }
    );

    const logGroup1 = new logs.LogGroup(this, "ModelInvocationLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup1.grantWrite(taskExecutionRole);


    const container = taskDefinition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_model_invocation"
      ),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost/model/service/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      containerName: "model_invocation",
      environment: {
        LOGGING_TABLE: modelInvocationLoggingTable.tableName,
        CLIENTS_TABLE: app_clients_table.tableName,
        COGNITO_USER_POOL_ID: cognitouserpool.userPoolId,
        REDIS_URL: serverless_redis.attrEndpointAddress,
        REDIS_PORT: "6379"
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "model_invocation",logGroup:logGroup1 }),
    });

    container.addPortMappings({ containerPort: 80, hostPort: 80 });

    const servicetargetGroup = new elbv2.ApplicationTargetGroup(
      this,
      "FoundationsModelInvocationTG"+uniqueCode,
      {
        vpc: vpc,
        port: 80,
        targetType: elbv2.TargetType.IP,
        healthCheck: {
          path: "/model/service/health",
        },
        protocol: elbv2.ApplicationProtocol.HTTP,
      }
    );
    listener.addAction("ModelInvocationAction"+uniqueCode, {
      priority: 1,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/model/*"])],
      action: elbv2.ListenerAction.forward([servicetargetGroup]),
    });
    const model_service = new ecs.FargateService(this, "ModelInvocationService", {
      cluster: cluster,
      taskDefinition: taskDefinition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });
    model_service.attachToApplicationTargetGroup(servicetargetGroup);


    /// End of Model Invocation Microservice

    // Document Processing Microservice

    const extraction_results_bucket = new s3.Bucket(this, "ExtractionResultsBucket"+uniqueCode, {
      bucketName: "foundations-extraction-results-"+uniqueCode,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryption: s3.BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: logBucket,
      serverAccessLogsPrefix: "extraction-results-access-logs/"
    });

    const extraction_source_bucket = new s3.Bucket(this, "ExtractionSourceBucket"+uniqueCode, {
      bucketName: "foundations-extraction-source-"+uniqueCode,
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryption: s3.BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: logBucket,
      serverAccessLogsPrefix: "extraction-source-access-logs/"
    });

     // Enforce TLS
    extraction_results_bucket.addToResourcePolicy(new iam.PolicyStatement({
      effect:iam.Effect.DENY,
      actions:["s3:*"],
      resources:[
        extraction_results_bucket.bucketArn,
        extraction_results_bucket.arnForObjects("*")
      ],
      conditions:{
        "Bool": {
          "aws:SecureTransport": "false"
        },
        "NumericLessThan": {
            "s3:TlsVersion": "1.2"
        }
      },
      principals:[new iam.AnyPrincipal()]
    }));

    extraction_results_bucket.addToResourcePolicy(new iam.PolicyStatement({
      actions: ["s3:GetObject", "s3:PutObject"],
      resources: [extraction_results_bucket.arnForObjects("*")],
      principals: [taskExecutionRole],
    }));

    extraction_source_bucket.addToResourcePolicy(new iam.PolicyStatement({
      actions: ["s3:GetObject", "s3:PutObject"],
      resources: [extraction_source_bucket.arnForObjects("*")],
      principals: [taskExecutionRole],
    }));

     // Enforce TLS
     extraction_results_bucket.addToResourcePolicy(new iam.PolicyStatement({
      effect:iam.Effect.DENY,
      actions:["s3:*"],
      resources:[
        extraction_results_bucket.bucketArn,
        extraction_results_bucket.arnForObjects("*")
      ],
      conditions:{
        "Bool": {
          "aws:SecureTransport": "false"
        },
        "NumericLessThan": {
            "s3:TlsVersion": "1.2"
        }
      },
      principals:[new iam.AnyPrincipal()]
    }));

    // Enforce TLS
    extraction_source_bucket.addToResourcePolicy(new iam.PolicyStatement({
      effect:iam.Effect.DENY,
      actions:["s3:*"],
      resources:[
        extraction_source_bucket.bucketArn,
        extraction_source_bucket.arnForObjects("*")
      ],
      conditions:{
        "Bool": {
          "aws:SecureTransport": "false"
        },
        "NumericLessThan": {
            "s3:TlsVersion": "1.2"
        }
      },
      principals:[new iam.AnyPrincipal()]
    })
  );

    extraction_results_bucket.grantReadWrite(taskExecutionRole);
    extraction_source_bucket.grantReadWrite(taskExecutionRole);
      

    const extraction_jobs_table = new dynamodb.TableV2(
      this,
      "ExtractionJobsTable",
      {
        tableName: "foundations_extraction_jobs_"+uniqueCode,
        partitionKey: { name: "job_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "app_id_index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const extraction_job_files_table = new dynamodb.TableV2(
      this,
      "ExtractionJobFilesTable",
      {
        tableName: "foundations_extraction_job_files_"+uniqueCode,
        partitionKey: { name: "job_id", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "file_name", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "job_id-index",
            partitionKey: { name: "job_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const chunking_jobs_table = new dynamodb.TableV2(
      this,
      "ChunkingJobsTable",
      {
        tableName: "foundations_chunking_jobs_"+uniqueCode,
        partitionKey: { name: "chunking_job_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "app_id_index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
          },
          {
            indexName: "extraction_job_id-index",
            partitionKey: { name: "extraction_job_id", type: dynamodb.AttributeType.STRING }
          }
        ],
      }
    );

    const chunking_job_files_table = new dynamodb.TableV2(
      this,
      "ChunkingJobFilesTable",
      {
        tableName: "foundations_chunk_job_files_"+uniqueCode,
        partitionKey: { name: "chunk_job_file_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "chunking_job_id-index",
            partitionKey: { name: "chunking_job_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const extraction_fifo_queue = new sqs.Queue(this, "FoundationsExtractionFifo"+uniqueCode, {
      queueName: "foundations_extraction_fifo_"+uniqueCode+".fifo",
      fifo: true,
      deduplicationScope: sqs.DeduplicationScope.MESSAGE_GROUP,
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: kmsKey

    });

    const chunking_fifo_queue = new sqs.Queue(this, "FoundationsChunkingFifo"+uniqueCode, {
      queueName: "foundations_chunking_fifo_"+uniqueCode+".fifo",
      fifo: true,
      deduplicationScope: sqs.DeduplicationScope.MESSAGE_GROUP,
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: kmsKey

    });

    const document_processing_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsDocProcessingTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsDocProcessingTaskDef"+uniqueCode,
      }
    );


    const logGroup2 = new logs.LogGroup(this, "DocumentProcessingLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup2.grantWrite(taskExecutionRole);

    const document_processing_container = document_processing_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_document_processing"
      ),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost/document/service/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      containerName: "document_processing",
      environment: {
        RESULTS_BUCKET_NAME: extraction_results_bucket.bucketName,
        SOURCE_BUCKET_NAME: extraction_source_bucket.bucketName,
        EXTRACTION_JOBS_TABLE: extraction_jobs_table.tableName,
        EXTRACTION_JOB_FILES_TABLE: extraction_job_files_table.tableName,
        QUEUE_URL: extraction_fifo_queue.queueUrl,
        COGNITO_USER_POOL_ID: cognitouserpool.userPoolId,
        CLIENTS_TABLE: app_clients_table.tableName,
        CHUNKING_JOBS_TABLE: chunking_jobs_table.tableName,
        CHUNKING_JOBS_FILES_TABLE: chunking_job_files_table.tableName,
        CHUNKING_QUEUE_URL: chunking_fifo_queue.queueUrl
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "document_processing", logGroup:logGroup2 }),
    });

    document_processing_container.addPortMappings({ containerPort: 80, hostPort: 80 });

    const document_processing_target_group = new elbv2.ApplicationTargetGroup(
      this,
      "FoundationsDocProcessingTG"+uniqueCode,
      {
        vpc: vpc,
        port: 80,
        targetType: elbv2.TargetType.IP,
        healthCheck: {
          path: "/document/service/health",
        },
        protocol: elbv2.ApplicationProtocol.HTTP,
      }
    );

    listener.addAction("DocumentProcessingAction"+uniqueCode, {
      priority: 2,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/document/*"])],
      action: elbv2.ListenerAction.forward([document_processing_target_group]),
    });

    const document_processing_service = new ecs.FargateService(this, "DocumentProcessingService", {
      cluster: cluster,
      taskDefinition: document_processing_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    document_processing_service.attachToApplicationTargetGroup(document_processing_target_group);

    /// End of Document Processing Microservice

    const logGroup3 = new logs.LogGroup(this, "ChunkingLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup3.grantWrite(taskExecutionRole);

    // Chunking Microservice, no endpoints, works off of SQS

    const chunking_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsChunkingTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsChunkingTaskDef"+uniqueCode,
      }
    );

    const chunking_container = chunking_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_chunking"
      ),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost/chunking/service/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      containerName: "chunking",
      environment: {
        QUEUE_URL : chunking_fifo_queue.queueUrl,
        RESULTS_S3_BUCKET : extraction_results_bucket.bucketName,
        CHUNKING_JOBS_TABLE : chunking_jobs_table.tableName,
        CHUNKING_JOBS_FILES_TABLE : chunking_job_files_table.tableName,
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "chunking", logGroup: logGroup3 }),
    });


    const chunking_service = new ecs.FargateService(this, "ChunkingService", {
      cluster: cluster,
      taskDefinition: chunking_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    // End of Chunking Microservice

    const logGroup4 = new logs.LogGroup(this, "ExtractionLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup4.grantWrite(taskExecutionRole);

    // Extraction Microservice, no endpoints, works off of SQS

    const extraction_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsExtractionTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsExtractionTaskDef"+uniqueCode,
      }
    );

    const extraction_container = extraction_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_extraction"
      ),
      containerName: "extraction",
      environment: {
        RESULTS_S3_BUCKET: extraction_results_bucket.bucketName,
        JOB_RESULTS_TABLE: extraction_jobs_table.tableName,
        JOB_FILES_TABLE: extraction_job_files_table.tableName,
        QUEUE_URL: extraction_fifo_queue.queueUrl,
        SOURCE_S3_BUCKET: extraction_source_bucket.bucketName,
        MAX_CONCURRENT_TASKS: '10',
        VISIBILITY_TIMEOUT: '600'
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "extraction", logGroup: logGroup4 }),
    });

    const extraction_service = new ecs.FargateService(this, "ExtractionService", {
      cluster: cluster,
      taskDefinition: extraction_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    /// End of Extraction Microservice


    // Vectorization Microservice

    const vector_store_table = new dynamodb.TableV2(
      this,
      "VectorStoreTable",
      {
        tableName: "foundations_vector_stores_"+uniqueCode,
        partitionKey: { name: "vector_store_id", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "app_id_index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const vector_store_index_table = new dynamodb.TableV2(
      this,
      "VectorStoreIndexTable",
      {
        tableName: "foundations_vector_indexes_"+uniqueCode,
        partitionKey: { name: "index_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "vector_store_id-index",
            partitionKey: { name: "vector_store_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const vector_jobs_table = new dynamodb.TableV2(
      this,
      "VectorJobsTable",
      {
        tableName: "foundations_vectorize_jobs_"+uniqueCode,
        partitionKey: { name: "vectorize_job_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "app_id-index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
          },
          {
            indexName: "vector_store_id-index",
            partitionKey: { name: "vector_store_id", type: dynamodb.AttributeType.STRING },
          }
        ],
      }
    );

    const vector_jobs_files_table = new dynamodb.TableV2(
      this,
      "VectorJobFilesTable",
      {
        tableName: "foundations_vectorize_job_files_"+uniqueCode,
        partitionKey: { name: "vectorize_job_file_id", type: dynamodb.AttributeType.STRING },
        globalSecondaryIndexes: [
          {
            indexName: "vectorize_job_id-index",
            partitionKey: { name: "vectorize_job_id", type: dynamodb.AttributeType.STRING }
          }
        ],
      }
    );

    


    const vectorizarion_fifo_queue = new sqs.Queue(this, "VectorizationFifoQueue"+uniqueCode, {
      queueName: "foundations_vectorize_fifo_"+uniqueCode+".fifo",
      fifo: true,
      deduplicationScope: sqs.DeduplicationScope.MESSAGE_GROUP,
      encryption: sqs.QueueEncryption.KMS,
      encryptionMasterKey: kmsKey

    });

    const logGroup5 = new logs.LogGroup(this, "VectorizeLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup5.grantWrite(taskExecutionRole);

    const vectorization_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsVectorizeTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsVectorizeTaskDef"+uniqueCode,
      }
    );

    const vectorization_container = vectorization_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_vectorization"
      ),
      containerName: "vectorization",
      environment: {   
        ACCESS_ROLE_ARN: taskExecutionRole.roleArn,
        VECTOR_STORES_TABLE : vector_store_table.tableName,
        VECTOR_STORES_INDEX_TABLE : vector_store_index_table.tableName,
        VECTORIZE_JOBS_TABLE : vector_jobs_table.tableName,
        VECTORIZE_JOB_FILES_TABLE : vector_jobs_files_table.tableName,
        JOBS_QUEUE_URL : vectorizarion_fifo_queue.queueUrl,
        CHUNK_JOBS_TABLE : chunking_jobs_table.tableName,
        CHUNK_JOB_FILES_TABLE : chunking_job_files_table.tableName,
        CLIENTS_TABLE: app_clients_table.tableName,
        AOSS_VPCE_ID: aossEP.attrId
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "vectorization", logGroup: logGroup5 }),
    });

    vectorization_container.addPortMappings({ containerPort: 80, hostPort: 80 });

    const vectorization_service = new ecs.FargateService(this, "VectorizationService", {
      cluster: cluster,
      taskDefinition: vectorization_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    const vectorization_target_group = new elbv2.ApplicationTargetGroup(
      this,
      "VectorizationTG"+uniqueCode,
      {
        vpc: vpc,
        port: 80,
        targetType: elbv2.TargetType.IP,
        healthCheck: {
          path: "/vector/service/health",
        },
        protocol: elbv2.ApplicationProtocol.HTTP,
      }
    );

    listener.addAction("VectorizationAction"+uniqueCode, {
      priority: 4,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/vector/*"])],
      action: elbv2.ListenerAction.forward([vectorization_target_group]),
    });


    vectorization_service.attachToApplicationTargetGroup(vectorization_target_group);


    /// Vector jobs process microservice, no endpoints, works off of SQS


    const logGroup6 = new logs.LogGroup(this, "VectorProcessLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup6.grantWrite(taskExecutionRole);

    const vj_process_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsVectorProcessTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsVectorProcessTaskDef"+uniqueCode,
      }
    );


    const vector_jobs_process_container = vj_process_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_vector_process"
      ),
      containerName: "vector_jobs_process",
      environment: {
        VECTORIZATION_QUEUE_URL : vectorizarion_fifo_queue.queueUrl,
        VECTORIZE_JOBS_TABLE : vector_jobs_table.tableName,
        VECTORIZE_JOB_FILES_TABLE : vector_jobs_files_table.tableName,
        RESULTS_S3_BUCKET : extraction_results_bucket.bucketName
      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "vector_jobs_process", logGroup: logGroup6 }),
    });

    const vector_jobs_process_service = new ecs.FargateService(this, "VectorJobsProcessService", {
      cluster: cluster,
      taskDefinition: vj_process_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    /// End of Vector Jobs Process Microservice


    /// End of Vectorization Microservice


    // Start of Prompt Template Management Microservice
    const promttemplatetable = new dynamodb.TableV2(
      this,
      "PromptTemplateTable",
      {
        tableName: "foundations_prompt_templates_"+uniqueCode,
        partitionKey: { name: "name", type: dynamodb.AttributeType.STRING },
        sortKey: { name: "version", type: dynamodb.AttributeType.NUMBER },
        globalSecondaryIndexes: [
          {
            indexName: "app_id-name-index",
            partitionKey: { name: "app_id", type: dynamodb.AttributeType.STRING },
            sortKey: { name: "name", type: dynamodb.AttributeType.STRING }
          }
        ],
      }
    );


    const logGroup7 = new logs.LogGroup(this, "PromptMgmtLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup7.grantWrite(taskExecutionRole);

    const prompt_template_task_definition = new ecs.FargateTaskDefinition
    (this, "FoundationsPromptMgmtTaskDef"+uniqueCode, {
      cpu: 256,
      memoryLimitMiB: 512,
      executionRole: taskExecutionRole,
      taskRole: taskExecutionRole,
      family: "FoundationsPromptMgmtTaskDef"+uniqueCode,
    });
    const prompt_template_container = prompt_template_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "foundations_prompt_template"
      ),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost/prompt/service/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      containerName: "prompt_template",
      environment: {
        PROMPT_TEMPLATE_TABLE : promttemplatetable.tableName,
        CLIENTS_TABLE : app_clients_table.tableName
            },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "prompt_template", logGroup: logGroup7 }),
    });
    prompt_template_container.addPortMappings({ containerPort: 80, hostPort: 80 });
    const prompt_template_target_group = new elbv2.ApplicationTargetGroup(
      this,
      "PromptTemplateTG"+uniqueCode,
      {
        vpc: vpc,
        port: 80,
        targetType: elbv2.TargetType.IP,
        healthCheck: {
          path: "/prompt/service/health",
        },
        protocol: elbv2.ApplicationProtocol.HTTP,
      }
    );
    listener.addAction("PromptTemplateAction"+uniqueCode, {
      priority: 5,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/prompt/*"])],
      action: elbv2.ListenerAction.forward([prompt_template_target_group]),
    });
    const prompt_template_service = new ecs.FargateService(
      this, "PromptTemplateService", {
      cluster: cluster,
      taskDefinition: prompt_template_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });
    prompt_template_service.attachToApplicationTargetGroup(prompt_template_target_group);

    /// End of Prompt Template Management Microservice
    /// End of Microservices block



    ////////////// ADMIN UI ///////////////

    /// S3 web hosting block

    // Create a WAF Web ACL
    // const webAcl = new wafv2.CfnWebACL(this, 'FoundationsWebACL', {
    //   defaultAction: {
    //     allow: {},
    //   },
    //   scope: 'CLOUDFRONT',
    //   visibilityConfig: {
    //     cloudWatchMetricsEnabled: true,
    //     metricName: 'foundations-web-acl',
    //     sampledRequestsEnabled: true,
    //   },
    //   rules: [
    //     {
    //       name: 'AWS-AWSManagedRulesCommonRuleSet',
    //       priority: 0,
    //       overrideAction: { none: {} },
    //       statement: {
    //         managedRuleGroupStatement: {
    //           vendorName: 'AWS',
    //           name: 'AWSManagedRulesCommonRuleSet',
    //         },
    //       },
    //       visibilityConfig: {
    //         cloudWatchMetricsEnabled: true,
    //         metricName: 'AWSManagedRulesCommonRuleSet',
    //         sampledRequestsEnabled: true,
    //       },
    //     },
    //   ],
    // });

    const siteBucket = new s3.Bucket(this, 'FoundationsSiteBucket'+uniqueCode, {
      bucketName: "foundations-site-"+uniqueCode,
      encryption: s3.BucketEncryption.S3_MANAGED,
      serverAccessLogsBucket: logBucket,
      serverAccessLogsPrefix: "foundations-site-access-logs/"
    })
    
    new CfnOutput(this, 
      'UI S3 Bucket Name', 
      { 
        value: siteBucket.bucketName,
        description: 'The bucket where the Admin Portal UI files will be hosted'
      });

     const cloudfront_origin_access_identity = new cloudfront.OriginAccessIdentity(this, 'FoundationsOriginAccessIdentity'+uniqueCode, {
        comment: 'Foundations Origin Access Identity'
      });

      const distribution = new cloudfront.Distribution(this, 'FoundationsDistribution'+uniqueCode, {
        defaultRootObject: "index.html",
        webAclId: props.webAclArn,
        defaultBehavior: {
          origin: new cloudfront_origins.S3Origin(siteBucket, {
            originAccessIdentity: cloudfront_origin_access_identity,
          }),
          viewerProtocolPolicy: cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
          compress: true,
          allowedMethods: cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS
        },
        logBucket: logBucket,
        logFilePrefix: "foundations-cloudfront-logs/",
        minimumProtocolVersion: cloudfront.SecurityPolicyProtocol.TLS_V1_2_2021,
      });


      

      // Associate the WAF Web ACL with the CloudFront distribution
      // new wafv2.CfnWebACLAssociation(this, 'FoundationsWebACLAssociation', {
      //   resourceArn: `arn:aws:cloudfront::${Aws.ACCOUNT_ID}:distribution/${distribution.distributionId}`,
      //   webAclArn: webAcl.attrArn,
      // });

      new CfnOutput(this, 'CloudFront Distribution URL', { value: 'https://'+distribution.distributionDomainName, description: 'URL for the Admin Portal UI.' });

      siteBucket.addToResourcePolicy(new iam.PolicyStatement({
        actions: ['s3:GetObject'],
        resources: [siteBucket.arnForObjects('*')],
        principals: [new iam.CanonicalUserPrincipal(cloudfront_origin_access_identity.cloudFrontOriginAccessIdentityS3CanonicalUserId)],
        // TLS condition
        conditions: {
          StringEquals: {
            'aws:SecureTransport': 'false',
          },
        },
      }));

      const admincognitouserpool = new cognito.UserPool(this, "FoundationsAdminUserPool"+uniqueCode, {
        userPoolName: "FoundationsAdminUserPool"+uniqueCode,
        signInAliases: {
          email: true,
        },
        autoVerify: {
          email: true,
        },
        standardAttributes: {
          email: {
            required: true,
            mutable: false,
          },
        },
        passwordPolicy: {
          minLength: 8,
          requireLowercase: true,
          requireUppercase: true,
          requireDigits: true,
          requireSymbols: true,
        }
      });

      new CfnOutput(this, 'Admin Cognito User Pool ID', { value: admincognitouserpool.userPoolId, description: 'The user pool ID for the Admin Portal UI Authentication' });

      const adminUser = new cognito.CfnUserPoolUser(
        this,
        "FoundationsAdminUserPoolUser"+uniqueCode,
        {
          userPoolId: admincognitouserpool.userPoolId,
          username: userEmail.valueAsString,
          userAttributes: [
            {
              name: "email",
              value: userEmail.valueAsString,
            },
            {
              name: "email_verified",
              value: "true",
            },
          ],
          desiredDeliveryMediums: ["EMAIL"],
        }
      );

      admincognitouserpool.addDomain("FoundationsAdminUserPoolDomain", {
        cognitoDomain: { domainPrefix: "foundationsadminui"+uniqueCode },
      });

      new CfnOutput(this, 'Admin Cognito User Pool Domain', { value: "foundationsadminui"+uniqueCode+".auth."+Aws.REGION+".amazoncognito.com", description: 'The domain for the Admin Portal UI Authentication' });

      const cognitoAdminUserPoolClient = new cognito.UserPoolClient(this, "FoundationsAdminUserPoolClient"+uniqueCode, {
        userPool: admincognitouserpool,
        userPoolClientName: "AdminUI"+uniqueCode,
        generateSecret: false,
        authFlows: {
          userSrp: true
        },
        supportedIdentityProviders: [
          cognito.UserPoolClientIdentityProvider.COGNITO,
        ],
        oAuth: {
          callbackUrls: ["https://"+distribution.distributionDomainName],
          logoutUrls: ["https://"+distribution.distributionDomainName],
          scopes: [
            cognito.OAuthScope.EMAIL,
            cognito.OAuthScope.OPENID
          ],
        },
      });

      cognitoAdminUserPoolClient.node.addDependency(distribution);

      new CfnOutput(this, 'Admin Cognito Client ID', { value: cognitoAdminUserPoolClient.userPoolClientId, description: 'The user pool client ID for the Admin Portal UI Authentication' });


      // Backend for the Admin UI will be hosted in the same ECS cluster as the other microservices. Below we add the backend service as a client to the user pool
      const cognitoAdminBackendClient = new cognito.UserPoolClient(this, "FoundationsAdminBackendClient"+uniqueCode, {
        userPool: cognitouserpool,
        userPoolClientName: "AdminBackend"+uniqueCode,
        generateSecret: true,
        authFlows: {
          userSrp: true
        },
        supportedIdentityProviders: [
          cognito.UserPoolClientIdentityProvider.COGNITO,
        ],
        oAuth: {
          scopes: [
            cognito.OAuthScope.resourceServer(resourceServer, readOnlyScope),
          ],
          // grant type client_credentials
          flows: {
            clientCredentials: true,
          },
        },
      });

    
    // New API Gateway Route for accessing the Admin Backend. This has no authorizer, because user authentication is done via the Admin UI
    const adminEndpoint = restApi.root.addResource("admin", {});
    const adminproxyresource = adminEndpoint.addResource("{proxy+}", {});

    const integration_options_admin = new apigwrestapi.Integration({
      type: apigwrestapi.IntegrationType.HTTP_PROXY,
      integrationHttpMethod: "ANY",
      uri: "http://" + nlb.loadBalancerDnsName + "/admin/{proxy}",
      options: {
        connectionType: apigwrestapi.ConnectionType.VPC_LINK,
        vpcLink: restapiVpcLink,
        requestParameters: {
          "integration.request.path.proxy": "method.request.path.proxy",
        },
      },
    });

    const admin_any_method = adminproxyresource.addMethod("ANY", integration_options_admin, {
      requestParameters: {
        "method.request.path.proxy": true,
      },
      methodResponses: [
        {
          statusCode: "200",
          responseParameters: {
            "method.response.header.Access-Control-Allow-Origin": true,
          },

        }
      ]
    });


    const logGroup8 = new logs.LogGroup(this, "FoundationsAdminLogGroup", {
      removalPolicy: cdk.RemovalPolicy.DESTROY,
      encryptionKey: kmsKey,
      retention: logs.RetentionDays.THREE_MONTHS,
    });

    logGroup8.grantWrite(taskExecutionRole);

    // Now we need to create the admin UI microservice
    const admin_task_definition = new ecs.FargateTaskDefinition(
      this,
      "FoundationsAdminTaskDef"+uniqueCode,
      {
        cpu: 256,
        memoryLimitMiB: 512,
        executionRole: taskExecutionRole,
        taskRole: taskExecutionRole,
        family: "FoundationsAdminTaskDef"+uniqueCode,
      }
    );
    


    const admin_container = admin_task_definition.addContainer("DefaultContainer", {
      image: ecs.ContainerImage.fromRegistry(
        Aws.ACCOUNT_ID+".dkr.ecr."+Aws.REGION+".amazonaws.com/" + "admin_backend_service"
      ),
      healthCheck: {
        command: ["CMD-SHELL", "curl -f http://localhost/admin/service/health || exit 1"],
        interval: cdk.Duration.seconds(30),
        timeout: cdk.Duration.seconds(5),
        retries: 3,
        startPeriod: cdk.Duration.seconds(60),
      },
      containerName: "AdminUIBackend",
      environment: {
        COGNITO_CLIENT_ID :cognitoAdminUserPoolClient.userPoolClientId,
        COGNITO_JWK_URL :"https://cognito-idp."+Aws.REGION+".amazonaws.com/"+admincognitouserpool.userPoolId+"/.well-known/jwks.json",
        AWS_REGION :Aws.REGION,
        USER_POOL_ID :admincognitouserpool.userPoolId,
        APP_USER_POOL_ID :cognitouserpool.userPoolId,
        PLATFORM_APP_CLIENT_ID :cognitoAdminBackendClient.userPoolClientId.toString(),
        PLATFORM_DOMAIN :"foundationsuserpool"+uniqueCode+".auth."+Aws.REGION+".amazoncognito.com",
        DYNAMODB_TABLE_NAME :app_clients_table.tableName,
        PLATFORM_BASE_URL :restApi.url,
        PLARFORM_SERVICES: "",
        OPENAPI_SPEC :"",
        INVOCATION_LOG_TABLE :modelInvocationLoggingTable.tableName,
        CORS_ORIGIN : "https://"+distribution.distributionDomainName,
        EXTRACTION_JOBS_TABLE: extraction_jobs_table.tableName,
        EXTRACTION_JOB_FILES_TABLE: extraction_job_files_table.tableName,
        CHUNKING_JOBS_TABLE: chunking_jobs_table.tableName,
        CHUNKING_JOBS_FILES_TABLE: chunking_job_files_table.tableName,
        PROMPT_TEMPLATE_TABLE: promttemplatetable.tableName,
        VECTOR_STORES_TABLE: vector_store_table.tableName,
        VECTOR_STORES_INDEX_TABLE: vector_store_index_table.tableName,
        VECTORIZE_JOBS_TABLE: vector_jobs_table.tableName,
        VECTORIZE_JOB_FILES_TABLE: vector_jobs_files_table.tableName,



      },
      logging: ecs.LogDrivers.awsLogs({ streamPrefix: "admin", logGroup: logGroup8 }),
    });

    admin_container.addPortMappings({ containerPort: 80, hostPort: 80 });

    new CfnOutput(this, 'Platform API Gateway URL', { value: restApi.url, description: 'The base URL for the Foundations Platform API' });


    const admin_target_group = new elbv2.ApplicationTargetGroup(
      this,
      "AdminTG"+uniqueCode,
      {
        vpc: vpc,
        port: 80,
        targetType: elbv2.TargetType.IP,
        healthCheck: {
          path: "/admin/service/health",
        },
        protocol: elbv2.ApplicationProtocol.HTTP,
      }
    );


    listener.addAction("AdminAction"+uniqueCode, {
      priority: 3,
      conditions: [elbv2.ListenerCondition.pathPatterns(["/admin/*"])],
      action: elbv2.ListenerAction.forward([admin_target_group]),
    });


    const admin_service = new ecs.FargateService(this, "AdminService", {
      cluster: cluster,
      taskDefinition: admin_task_definition,
      desiredCount: 1,
      vpcSubnets: {subnets: vpc.selectSubnets({subnetType: ec2.SubnetType.PRIVATE_WITH_EGRESS}).subnets},
      securityGroups: [securityGroup],
    });

    admin_service.attachToApplicationTargetGroup(admin_target_group);

    admin_service.node.addDependency(model_service);
    admin_service.node.addDependency(document_processing_service);
    admin_service.node.addDependency(prompt_template_service);

    adminproxyresource.addCorsPreflight({
      allowOrigins: ["https://"+distribution.distributionDomainName],
      allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
      allowHeaders: ["Content-Type", "X-Amz-Date", "Authorization", "X-Api-Key", "X-Amz-Security-Token", "X-Amz-User-Agent"],
      allowCredentials: true

    });

  }
}
