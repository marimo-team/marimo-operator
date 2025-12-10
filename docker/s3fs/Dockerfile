FROM alpine:3.19

RUN apk add --no-cache \
    s3fs-fuse \
    fuse \
    ca-certificates \
    && rm -rf /var/cache/apk/*

# s3fs needs /dev/fuse
RUN mkdir -p /dev && mknod /dev/fuse c 10 229 || true

ENTRYPOINT ["/bin/sh", "-c"]
