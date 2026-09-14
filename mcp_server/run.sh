#!/bin/sh
# Launched by the AWS Lambda Web Adapter (see infra/mcp.tf) to run this ASGI
# app as a local HTTP server the adapter proxies Lambda invocations to.
exec python3 -m uvicorn server:app --host 0.0.0.0 --port "${PORT:-8000}"
