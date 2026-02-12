"""AWS tool: S3, EC2, CloudWatch, Lambda, Logs operations."""

from __future__ import annotations

from typing import Any

from nanobot.agent.tools.base import Tool


class AWSTool(Tool):
    """Tool for AWS service operations using boto3."""

    def __init__(self, region: str = "us-east-1", profile: str | None = None):
        self._region = region
        self._profile = profile
        self._session = None

    @property
    def name(self) -> str:
        return "aws"

    @property
    def description(self) -> str:
        return (
            "Interact with AWS services. "
            "Services: s3 (list/get/put), ec2 (list/status), "
            "cloudwatch (metrics), lambda (list/invoke), logs (query). "
            "Read operations are auto-approved; mutations require approval."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "service": {
                    "type": "string",
                    "enum": ["s3", "ec2", "cloudwatch", "lambda", "logs"],
                    "description": "AWS service to use",
                },
                "action": {
                    "type": "string",
                    "description": "Service-specific action (e.g. list, get, put, invoke, query)",
                },
                "params": {
                    "type": "object",
                    "description": "Action-specific parameters",
                },
            },
            "required": ["service", "action"],
        }

    def _get_session(self):
        if self._session is None:
            import boto3
            kwargs = {"region_name": self._region}
            if self._profile:
                kwargs["profile_name"] = self._profile
            self._session = boto3.Session(**kwargs)
        return self._session

    async def execute(self, **kwargs: Any) -> str:
        service = kwargs.get("service", "")
        action = kwargs.get("action", "")
        params = kwargs.get("params", {}) or {}

        try:
            if service == "s3":
                return await self._s3(action, params)
            elif service == "ec2":
                return await self._ec2(action, params)
            elif service == "cloudwatch":
                return await self._cloudwatch(action, params)
            elif service == "lambda":
                return await self._lambda(action, params)
            elif service == "logs":
                return await self._logs(action, params)
            else:
                return f"Unknown AWS service: {service}"
        except Exception as e:
            return f"AWS error: {e}"

    async def _s3(self, action: str, params: dict) -> str:
        import asyncio
        s3 = self._get_session().client("s3")

        if action == "list":
            bucket = params.get("bucket")
            if bucket:
                prefix = params.get("prefix", "")
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: s3.list_objects_v2(Bucket=bucket, Prefix=prefix, MaxKeys=50)
                )
                objects = result.get("Contents", [])
                lines = [f"  {o['Key']} ({o['Size']} bytes)" for o in objects[:50]]
                return f"S3 objects in {bucket}/{prefix} ({len(objects)}):\n" + "\n".join(lines)
            else:
                result = await asyncio.get_event_loop().run_in_executor(
                    None, s3.list_buckets
                )
                buckets = [b["Name"] for b in result.get("Buckets", [])]
                return f"S3 Buckets ({len(buckets)}):\n" + "\n".join(f"  {b}" for b in buckets)

        elif action == "get":
            bucket = params.get("bucket", "")
            key = params.get("key", "")
            if not bucket or not key:
                return "Error: bucket and key required"
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: s3.get_object(Bucket=bucket, Key=key)
            )
            body = result["Body"].read()
            if len(body) > 5000:
                return f"Object {key}: {len(body)} bytes (too large to display)"
            try:
                return body.decode("utf-8")
            except UnicodeDecodeError:
                return f"Object {key}: {len(body)} bytes (binary)"

        elif action == "put":
            bucket = params.get("bucket", "")
            key = params.get("key", "")
            content = params.get("content", "")
            if not bucket or not key:
                return "Error: bucket and key required"
            await asyncio.get_event_loop().run_in_executor(
                None, lambda: s3.put_object(Bucket=bucket, Key=key, Body=content.encode())
            )
            return f"Uploaded to s3://{bucket}/{key}"

        return f"Unknown S3 action: {action}"

    async def _ec2(self, action: str, params: dict) -> str:
        import asyncio
        ec2 = self._get_session().client("ec2")

        if action in ("list", "status"):
            result = await asyncio.get_event_loop().run_in_executor(
                None, ec2.describe_instances
            )
            lines = []
            for r in result.get("Reservations", []):
                for i in r.get("Instances", []):
                    name = ""
                    for tag in i.get("Tags", []):
                        if tag["Key"] == "Name":
                            name = tag["Value"]
                    state = i["State"]["Name"]
                    itype = i.get("InstanceType", "?")
                    ip = i.get("PublicIpAddress", "none")
                    lines.append(f"  {name or i['InstanceId']}: {state} ({itype}, IP: {ip})")
            return f"EC2 Instances ({len(lines)}):\n" + "\n".join(lines) if lines else "No EC2 instances."

        return f"Unknown EC2 action: {action}"

    async def _cloudwatch(self, action: str, params: dict) -> str:
        import asyncio
        cw = self._get_session().client("cloudwatch")

        if action == "metrics":
            namespace = params.get("namespace", "")
            kwargs = {}
            if namespace:
                kwargs["Namespace"] = namespace
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: cw.list_metrics(**kwargs)
            )
            metrics = result.get("Metrics", [])[:30]
            lines = [f"  {m['Namespace']}/{m['MetricName']}" for m in metrics]
            return f"CloudWatch Metrics ({len(metrics)}):\n" + "\n".join(lines)

        return f"Unknown CloudWatch action: {action}"

    async def _lambda(self, action: str, params: dict) -> str:
        import asyncio
        lam = self._get_session().client("lambda")

        if action == "list":
            result = await asyncio.get_event_loop().run_in_executor(
                None, lam.list_functions
            )
            functions = result.get("Functions", [])
            lines = [f"  {f['FunctionName']} ({f.get('Runtime', '?')})" for f in functions[:30]]
            return f"Lambda Functions ({len(functions)}):\n" + "\n".join(lines)

        elif action == "invoke":
            name = params.get("name", "")
            payload = params.get("payload", "{}")
            if not name:
                return "Error: function name required"
            import json
            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: lam.invoke(
                    FunctionName=name,
                    Payload=json.dumps(payload) if isinstance(payload, dict) else payload,
                )
            )
            response_payload = result["Payload"].read().decode()
            return f"Lambda {name} result: {response_payload[:3000]}"

        return f"Unknown Lambda action: {action}"

    async def _logs(self, action: str, params: dict) -> str:
        import asyncio
        logs = self._get_session().client("logs")

        if action == "query":
            group = params.get("log_group", "")
            query = params.get("query", "fields @timestamp, @message | sort @timestamp desc | limit 20")
            if not group:
                return "Error: log_group required"

            import time
            end_time = int(time.time())
            start_time = end_time - 3600  # Last hour

            result = await asyncio.get_event_loop().run_in_executor(
                None, lambda: logs.start_query(
                    logGroupName=group,
                    startTime=start_time,
                    endTime=end_time,
                    queryString=query,
                )
            )
            query_id = result["queryId"]

            # Poll for results
            for _ in range(10):
                await asyncio.sleep(1)
                result = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: logs.get_query_results(queryId=query_id)
                )
                if result["status"] == "Complete":
                    lines = []
                    for row in result.get("results", [])[:30]:
                        fields = {f["field"]: f["value"] for f in row}
                        lines.append(f"  {fields.get('@timestamp', '?')}: {fields.get('@message', '?')[:200]}")
                    return f"Log results ({len(lines)}):\n" + "\n".join(lines)

            return "Query timed out."

        return f"Unknown Logs action: {action}"
