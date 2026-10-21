FROM --platform=$BUILDPLATFORM golang:1.24.8-alpine3.22 AS builder

ARG TARGETOS
ARG TARGETARCH
ARG MINIO_VERSION=RELEASE.2025-10-15T17-29-55Z
ARG MINIO_COMMIT=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a
ARG MINIO_SHORT_COMMIT=9e49d5e7a648

ENV CGO_ENABLED=0

RUN GOOS=${TARGETOS} GOARCH=${TARGETARCH} go install -trimpath -ldflags="-s -w \
    -X github.com/minio/minio/cmd.Version=${MINIO_VERSION} \
    -X github.com/minio/minio/cmd.ReleaseTag=${MINIO_VERSION} \
    -X github.com/minio/minio/cmd.CommitID=${MINIO_COMMIT} \
    -X github.com/minio/minio/cmd.ShortCommitID=${MINIO_SHORT_COMMIT} \
    -X github.com/minio/minio/cmd.CopyrightYear=2025" \
    github.com/minio/minio@${MINIO_VERSION}

FROM alpine:3.22

RUN apk add --no-cache ca-certificates curl \
    && addgroup -S minio \
    && adduser -S -G minio -h /home/minio minio \
    && mkdir -p /data /home/minio \
    && chown minio:minio /data /home/minio

COPY --from=builder /go/bin/minio /usr/local/bin/minio

USER minio

VOLUME ["/data"]
EXPOSE 9000
ENTRYPOINT ["minio"]
CMD ["server", "/data", "--console-address", ":9001"]
