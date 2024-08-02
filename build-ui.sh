#!/bin/bash

# Prompt for inputs
read -p "Enter AWS Region: " region
read -p "Enter Admin Cognito User Pool ID: " userPoolId
read -p "Enter Admin Cognito Client ID: " clientId
read -p "Enter CloudFront Distribution URL: " cloudfrontUrl
read -p "Enter Platform API Gateway URL: " apiUrl
read -p "Enter UI S3 Bucket Name: " bucketName
read -p "Enter Admin Cognito User Pool Domain: " cognitoDomain

# Replace placeholders in cognito-config.js
cognitoConfigPath="./admin-ui/frontend/foundations-admin/plugins/cognito-config.js"
sed -i '' "s|<region>|$region|g" $cognitoConfigPath
sed -i '' "s|<user_pool_id>|$userPoolId|g" $cognitoConfigPath
sed -i '' "s|<client_id>|$clientId|g" $cognitoConfigPath
sed -i '' "s|<redirect_uri>|$cloudfrontUrl|g" $cognitoConfigPath
sed -i '' "s|<logout_uri>|$cloudfrontUrl|g" $cognitoConfigPath
sed -i '' "s|<cognito_domain>|$cognitoDomain|g" $cognitoConfigPath

# Replace placeholders in nuxt.config.ts
nuxtConfigPath="./admin-ui/frontend/foundations-admin/nuxt.config.ts"
sed -i '' "s|<your-api-gateway-url>|$apiUrl|g" $nuxtConfigPath
sed -i '' "s|<cognito_domain>|$cognitoDomain|g" $nuxtConfigPath

cd ./admin-ui/frontend/foundations-admin/
sudo npm install
# Run the existing upload script
sudo rm -rf .output
sudo rm -rf dist
sudo rm -rf .nuxt
sudo npx nuxi generate  
sudo -E aws s3 sync .output/public s3://$bucketName