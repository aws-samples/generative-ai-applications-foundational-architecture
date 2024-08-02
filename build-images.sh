#!/bin/bash

# Variables
ACCOUNT_ID=$1
REGION=$2
CONFIG_FILE="config.txt"

# Function to check if a command exists
command_exists() {
  command -v "$1" >/dev/null 2>&1
}

# Check for required tools
if ! command_exists aws; then
  echo "Error: AWS CLI is not installed. Please install AWS CLI to continue."
  exit 1
fi

if ! command_exists docker; then
  echo "Error: Docker is not installed. Please install Docker to continue."
  exit 1
fi

if [ -z "$ACCOUNT_ID" ] || [ -z "$REGION" ]; then
  echo "Usage: $0 <AWS_ACCOUNT_ID> <AWS_REGION>"
  exit 1
fi

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
  echo "Error: Docker daemon is not running. Please start the Docker daemon to continue."
  exit 1
fi

REPO_URL="$ACCOUNT_ID.dkr.ecr.$REGION.amazonaws.com"

# Login to ECR
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $REPO_URL

# Function to create ECR repository if it doesn't exist
create_ecr_repo() {
  REPO_NAME=$1
  aws ecr describe-repositories --repository-names $REPO_NAME --region $REGION > /dev/null 2>&1
  if [ $? -ne 0 ]; then
    aws ecr create-repository --repository-name $REPO_NAME --image-scanning-configuration scanOnPush=true --region $REGION
  fi
}

# Array to keep track of successful image pushes
SUCCESSFUL_IMAGES=()

# Read config file and process each line
while IFS= read -r line || [ -n "$line" ]; do
  # Skip empty lines
  if [ -z "$line" ]; then
    continue
  fi

  # Split the line into remote container name and local folder path
  REMOTE_CONTAINER_NAME=$(echo $line | awk '{print $1}')
  LOCAL_FOLDER_PATH=$(echo $line | awk '{print $2}')

  # Construct the full image name
  IMAGE_NAME="$REPO_URL/$REMOTE_CONTAINER_NAME:latest"

  # Create the ECR repository if it doesn't exist
  create_ecr_repo $REMOTE_CONTAINER_NAME

  # Build the Docker image
  echo "Building Docker image for $LOCAL_FOLDER_PATH..."
  docker build --no-cache -t $REMOTE_CONTAINER_NAME:latest $LOCAL_FOLDER_PATH
  if [ $? -ne 0 ]; then
    echo "Error: Failed to build Docker image for $LOCAL_FOLDER_PATH."
    continue
  fi

  # Tag the Docker image
  echo "Tagging Docker image as $IMAGE_NAME..."
  docker tag $REMOTE_CONTAINER_NAME:latest $IMAGE_NAME
  if [ $? -ne 0 ]; then
    echo "Error: Failed to tag Docker image $IMAGE_NAME."
    continue
  fi

  # Push the Docker image to ECR
  echo "Pushing Docker image to $IMAGE_NAME..."
  docker push $IMAGE_NAME
  if [ $? -ne 0 ]; then
    echo "Error: Failed to push Docker image $IMAGE_NAME."
    continue
  fi

  # Wait for a few seconds to ensure the push is complete
  sleep 10

  # Add to successful images array
  SUCCESSFUL_IMAGES+=("$IMAGE_NAME")

done < $CONFIG_FILE

# Check if all images were created and pushed
TOTAL_IMAGES=$(grep -v -e '^\s*$' $CONFIG_FILE | wc -l)
SUCCESSFUL_COUNT=${#SUCCESSFUL_IMAGES[@]}

echo "Total images to be created and pushed: $TOTAL_IMAGES"
echo "Total successfully created and pushed images: $SUCCESSFUL_COUNT"

if [ $SUCCESSFUL_COUNT -eq $TOTAL_IMAGES ]; then
  echo "All images were successfully created and pushed."
else
  echo "The following images were successfully created and pushed:"
  for IMAGE in "${SUCCESSFUL_IMAGES[@]}"; do
    echo "$IMAGE"
  done
  echo "Some images failed to be created or pushed. Please check the logs for details."
fi

echo "Script execution completed."
