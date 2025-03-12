# Stage 1: Build Stage
FROM python:3.10-alpine AS builder

# Copy all necessary files for the build
COPY ./src ./src
COPY ./pyproject.toml .

# Build a wheel from the public Git repo
RUN pip wheel --no-cache-dir --no-deps --wheel-dir=/wheels .

# Stage 2: Build the final image
FROM python:3.10-alpine

ARG VERSION
ARG GIT_SHA

LABEL version="${VERSION}"
LABEL git-sha="${GIT_SHA}"
LABEL description="This is a Docker image for the BatControl project."
LABEL maintainer="matthias.strubel@aod-rpg.de"

# Copy the built wheel from the builder stage and install it
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

ENV BATCONTROL_VERSION=${VERSION}
ENV BATCONTROL_GIT_SHA=${GIT_SHA}
# Set default timezone to UTC, override with -e TZ=Europe/Berlin or similar 
# when starting the container 
# or set the timezone in docker-compose.yml in the environment section,
ENV TZ=UTC  

# Create the app directory and copy the app files
RUN mkdir -p /app /app/logs /app/config
WORKDIR /app

# Copy other necessary runtime files (like config templates or entrypoint scripts)
COPY LICENSE ./
COPY config/load_profile_default.csv ./config/load_profile.csv
COPY config/load_profile_default.csv ./default_load_profile.csv
COPY config ./config_template
COPY entrypoint.sh ./
COPY entrypoint_ha.sh ./
RUN chmod +x entrypoint.sh entrypoint_ha.sh

VOLUME ["/app/logs", "/app/config"]

CMD ["/bin/sh", "/app/entrypoint.sh"]
