# Implementation Guide

#### Pre-requisites

Before you begin, ensure you have the following:

1. **AWS Account**: You must have an AWS account with necessary permissions to create resources.
2. **AWS CLI**: Installed and configured on your machine. Follow [this guide](https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html) to install AWS CLI.
3. **IAM User**: A user with admin privileges configured in AWS CLI using ```aws configure``` in the "default" profile. 
4. **Node.js and npm**: Installed on your machine. Follow [this guide](https://nodejs.org/en/download/package-manager) for installation. If you are using an EC2 instance, you can follow [this guide](https://docs.aws.amazon.com/sdk-for-javascript/v2/developer-guide/setting-up-node-on-ec2-instance.html)
6. **Docker**: Ensure Docker is installed and running on your machine. Follow this guide for installation.
7. **Git**: Installed on your machine. Follow [this guide](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) for installation.
8. **Email**: An email address to be used as admin user of the platform. Admin Portal password will be sent to this email.
9. ***Install CDK CLI*** : Run ``` npm install -g aws-cdk ``` to install CDK
10. **Manage access to Amazon Bedrock foundation models**: You must have enabled foundational models in Amazon Bedrock. Follow [this guide](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) to manage access.
    

#### Implementation Steps
1. #### Clone repository
```
git clone https://github.com/aws-samples/generative-ai-applications-foundational-architecture.git
```
This will clone the repository to your local workstation.
It will have the following folder structure.
```
generative-ai-applications-foundational-architecture
    ├── admin-ui # The Admin portal, frontend and backend
    │   ├── backend
    │   └── frontend
    ├── cdk # CDK application to deploy infrastructure
    │   └── GenAIFoundations
    ├── cookbook # Usage samples, notebooks and sample apps
    │   ├── notebooks
    │   ├── sample-apps
    │   └── sdk # SDK
    ├── docs  # All documentation
    │   ├── adminportal.md
    │   ├── api_docs
    │   ├── implementation.md
    │   └── microservices.md
    ├── image
    │   ├── HighLevelArchitecture.png
    │   ├── adminapiplayground.png
    │   ├── adminlogin.gif
    │   ├── adminmetrics.gif
    │   ├── adminonboardapp.gif
    │   ├── adminservices.png
    │   ├── architecture.png
    │   ├── authentication_flow.png
    │   ├── chunkingprocess.png
    │   ├── extractionprocess.png
    │   └── how-it-works.png
    ├── services # Microservices with Docker files
    │   ├── foundations_chunking
    │   ├── foundations_document_processing
    │   ├── foundations_extraction
    │   ├── foundations_model_invocation
    │   ├── foundations_prompt_management
    │   ├── foundations_vector_job_process
    │   └── foundations_vectorization
    └── testing # Test scripts
        ├── auth
        └── models
    ├── build-images.sh # Builds docker images and pushes them to ECR
    ├── build-ui.sh # Builds UI locally and pushes the assets to S3
    ├── config.txt  # List of microservices to build. Modify this if you want to push only specific images.
```
2. #### Check for Docker daemon status and ensure it is up and running. In case DOcker is not running, please start the daemon and rerun the command to confirm the status.

```
docker info > /dev/null 2>&1 && echo "Docker is up and running" || echo "Docker is not running"
```

3. #### Create IAM Service Linked Role for ECS
```
aws iam create-service-linked-role --aws-service-name ecs.amazonaws.com
```
> Note: Execute this command only if it is a new account where no ECS cluster was created. You can check if a service linked role for ECS already exists in IAM console.
4. #### Build docker container images and push them to ECR repository
```
sh ./build-images.sh <aws-account-id> <aws-region>
```
> ⚠️ **Important: After sucessful completion of the script login to AWS Account and navigate to ECR console and confirm below repositories and their correspoding images are available**

> If some of images are not pushed to ECR, please modify config.txt file and re-run the script.
- foundations_model_invocation
- foundations_document_processing
- foundations_extraction
- foundations_chunking
- foundations_vectorization
- foundations_vector_process
- foundations_prompt_management
- admin_backend_service


5. #### Navigate to cdk project
```
cd cdk/GenAIFoundations
```
6. #### Bootstrap your cdk project
Run the following commands
```
npm install
cdk bootstrap -c VPC_CIDR='<your-vpc-cidr>'
```
> VPC CIDR will be used to create a new VPC where the ECS cluster will be hosted
7. #### Synthesize Cloudformation Template
```
cdk synth -c VPC_CIDR='<your-vpc-cidr>' --parameters userEmail="<your-email>"
```
> Execute this step if you want to use a static cloudformation template to deploy the stack. If you want to use cdk deploy to auto deploy the stack, skip to the next step.
> userEmail is the email that will be used to provide access to the admin portal. Password will be sent to this email address.
8. #### Deploy the stack using ```cdk deploy```
```
cdk deploy -c VPC_CIDR='<your-vpc-cidr>' --parameters userEmail="<your-email>" --all
```
> Skip this step if you are deploying using static Cloudformation Template (step 6)
9. #### Navigate back to the root of the project
```
cd ../..
```
10. #### Make a note of the Cloudformation Stack outputs
> The following parameters will be outputted after the stack deployment completes. We will use these values as inputs in the next step.


| Parameter Name     | Details |
---------------------|----------------------------
AdminCognitoClientID |	Admin Cognito Client ID |
AdminCognitoUserPoolDomain | Admin Cognito User Pool Domain |
AdminCognitoUserPoolID | Admin Cognito User Pool ID
CloudFrontDistributionURL | CloudFront Distribution URL |
PlatformAPIGatewayURL |	Platform API Gateway URL |
UIS3BucketName | UI S3 Bucket Name |

11. #### Build and deploy the UI
> Note: Run below code using sudo credentials.

```
sudo sh ./build-ui.sh
```
> Please refer to the table in step 10 to enter the inputs to this script.

> After you complete the steps, you can log in to the Admin Portal using the Cloudfront Distribution URL. For steps on using Admin Portal and onboarding new application follow [this guide](./docs/adminportal.md)

> Please make sure you have enabled models on Bedrock. Follow [this guide](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html) to manage access.