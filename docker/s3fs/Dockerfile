ARG ALPINE_VERSION=3.20
FROM alpine:${ALPINE_VERSION} AS build

ARG S3FS_VERSION=v1.94

RUN apk --no-cache add \
    ca-certificates build-base git alpine-sdk libcurl \
    automake autoconf libxml2-dev fuse-dev curl-dev && \
    git clone --depth 1 --branch ${S3FS_VERSION} \
        https://github.com/s3fs-fuse/s3fs-fuse.git && \
    cd s3fs-fuse && \
    ./autogen.sh && \
    ./configure --prefix=/usr && \
    make -j && \
    make install

FROM alpine:${ALPINE_VERSION}

COPY --from=build /usr/bin/s3fs /usr/bin/s3fs

RUN apk --no-cache add ca-certificates fuse libxml2 libcurl libgcc libstdc++ tini && \
    echo "user_allow_other" >> /etc/fuse.conf && \
    s3fs --version

ENTRYPOINT ["tini", "-g", "--", "/bin/sh", "-c"]
