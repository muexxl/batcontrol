#!/bin/sh

# Get the current commit SHA
GIT_SHA=$(git rev-parse HEAD)

# Get the current Git reference name (branch or tag)
GIT_REF_NAME=$(git symbolic-ref -q --short HEAD || git describe --tags --exact-match)

# Set the VERSION value
if [ -n "$GIT_REF_NAME" ]; then
  VERSION=$GIT_REF_NAME
else
  VERSION="snapshot"
fi

# Print the VERSION value
echo "SHA: $GIT_SHA .. VERSION: $VERSION"

# Build the Docker image with build arguments
docker buildx build . -t hashtagknorke:batcontrol --build-arg GIT_SHA=$GIT_SHA --build-arg VERSION=$VERSION