"""Cloud processing adapters. External calls are disabled until deployment enables them.

Provider SDKs/REST contracts are isolated so tests can exercise them without credentials.
"""

import asyncio
import copy
import io
import json
import wave
from dataclasses import dataclass
from urllib.parse import quote
from uuid import uuid4
from xml.sax.saxutils import escape

import httpx

from pms_api.core.common import require
from pms_api.integrations.contracts import synthesis_parameters
from pms_api.integrations.vault import CredentialVault


@dataclass
class ProviderResult:
    status: str
    job_id: str | None = None
    result: dict | None = None
    audio: bytes | None = None
    error: str | None = None


class AWSProvider:
    def __init__(self, settings, connection, credentials):
        self.settings = settings
        self.config = copy.deepcopy(connection.settings)
        self.auth = connection.auth_mode
        self.credentials = credentials
        self._session = None

    def session(self):
        import boto3
        from botocore.config import Config

        if self._session:
            return self._session
        options = {"region_name": self.config["region"]}
        if self.auth == "access_key":
            options.update(
                aws_access_key_id=self.credentials["access_key_id"],
                aws_secret_access_key=self.credentials["secret_access_key"],
                aws_session_token=self.credentials.get("session_token"),
            )
        session = boto3.Session(**options)
        if self.auth == "assume_role":
            token = session.client(
                "sts", config=Config(connect_timeout=5, read_timeout=15, retries={"max_attempts": 1})
            ).assume_role(
                RoleArn=self.config["role_arn"],
                RoleSessionName="pms-api",
                ExternalId=self.config["external_id"],
            )["Credentials"]
            session = boto3.Session(
                region_name=self.config["region"],
                aws_access_key_id=token["AccessKeyId"],
                aws_secret_access_key=token["SecretAccessKey"],
                aws_session_token=token["SessionToken"],
            )
        self._session = session
        return session

    def client(self, name):
        from botocore.config import Config

        return self.session().client(
            name,
            config=Config(
                connect_timeout=5,
                read_timeout=self.settings.provider_timeout_seconds,
                # No hidden transport retry after a potentially billable request.
                # The durable worker owns reconciliation and retry decisions.
                retries={"total_max_attempts": 1},
            ),
        )

    def input_key(self, run_id, extension):
        return f"{self.config.get('staging_prefix', 'pms').strip('/')}/{run_id}/input.{extension}"

    def output_key(self, run_id):
        return f"{self.config.get('staging_prefix', 'pms').strip('/')}/{run_id}/transcript.json"

    async def stage(self, run_id, data, extension):
        bucket = self.config.get("staging_bucket")
        require(bool(bucket), "staging_required", "Configure S3 staging for this operation", 409)
        await asyncio.to_thread(
            self.client("s3").put_object, Bucket=bucket, Key=self.input_key(run_id, extension), Body=data
        )

    async def validate(self, operation, sample=False):
        require(not sample, "sample_via_run", "Use a bounded processing run for an end-to-end sample test")
        await asyncio.to_thread(self.client("sts").get_caller_identity)
        if operation == "audio.synthesize":
            await asyncio.to_thread(self.client("polly").describe_voices)
        else:
            bucket = self.config.get("staging_bucket")
            require(bool(bucket), "staging_required", "Configure S3 staging")
            key = f"{self.config.get('staging_prefix', 'pms').strip('/')}/validation/{uuid4()}.txt"
            client = self.client("s3")
            try:
                await asyncio.to_thread(client.put_object, Bucket=bucket, Key=key, Body=b"pms-validation")
                await asyncio.to_thread(client.head_object, Bucket=bucket, Key=key)
            finally:
                await asyncio.to_thread(client.delete_object, Bucket=bucket, Key=key)
            if operation == "audio.transcribe":
                await asyncio.to_thread(self.client("transcribe").list_transcription_jobs, MaxResults=1)
            else:
                await asyncio.to_thread(self.client("rekognition").list_stream_processors, MaxResults=1)
        return True

    async def submit(self, run_id, operation, section, request):
        name = "pms-" + str(run_id)
        if operation == "audio.synthesize":
            options = synthesis_parameters("aws_polly", section, request)
            output_format, voice = options["format"], options["voice"]
            output = await asyncio.to_thread(
                self.client("polly").synthesize_speech,
                Text=request["text"],
                TextType="text",
                VoiceId=voice,
                OutputFormat={"wav": "pcm", "ogg": "ogg_vorbis"}.get(output_format, output_format),
                SampleRate="16000" if output_format in {"wav", "pcm"} else "24000",
                **({"LanguageCode": section["language"]} if section.get("language") else {}),
            )
            try:
                audio = await asyncio.to_thread(output["AudioStream"].read)
            finally:
                output["AudioStream"].close()
            if output_format == "wav":
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(16000)
                    wav.writeframes(audio)
                audio = buffer.getvalue()
            return ProviderResult(
                "succeeded",
                result={
                    "format": output_format,
                    "sample_rate": 16000 if output_format in {"wav", "pcm"} else 24000,
                    "channels": 1,
                },
                audio=audio,
            )
        bucket = self.config["staging_bucket"]
        key = self.input_key(run_id, request["format"])
        if operation == "audio.transcribe":
            params = {
                "TranscriptionJobName": name,
                "Media": {"MediaFileUri": f"s3://{bucket}/{key}"},
                "MediaFormat": request["format"],
                "OutputBucketName": bucket,
                "OutputKey": self.output_key(run_id),
            }
            params.update(
                {"LanguageCode": section["language"]}
                if section.get("language")
                else {"IdentifyLanguage": True}
            )
            try:
                await asyncio.to_thread(self.client("transcribe").start_transcription_job, **params)
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") != "ConflictException":
                    raise
            return ProviderResult("running", job_id=name)
        result = await asyncio.to_thread(
            self.client("rekognition").start_label_detection,
            Video={"S3Object": {"Bucket": bucket, "Name": key}},
            ClientRequestToken=str(run_id),
            JobTag=name,
        )
        return ProviderResult("running", job_id=result["JobId"])

    async def poll(self, run_id, operation, job_id):
        if operation == "audio.transcribe":
            output = await asyncio.to_thread(
                self.client("transcribe").get_transcription_job, TranscriptionJobName=job_id
            )
            job = output["TranscriptionJob"]
            state = job["TranscriptionJobStatus"]
            if state == "FAILED":
                return ProviderResult("failed", job_id, error="provider_failed")
            if state != "COMPLETED":
                return ProviderResult("running", job_id)
            data = await asyncio.to_thread(
                self.client("s3").get_object,
                Bucket=self.config["staging_bucket"],
                Key=self.output_key(run_id),
            )
            try:
                payload = await asyncio.to_thread(data["Body"].read, 1048577)
            finally:
                data["Body"].close()
            require(
                len(payload) <= 1048576, "provider_result_too_large", "Provider result exceeds storage limit"
            )
            value = json.loads(payload)
            return ProviderResult(
                "succeeded",
                job_id,
                result={
                    "text": " ".join(t["transcript"] for t in value.get("results", {}).get("transcripts", []))
                },
            )
        labels: list[dict] = []
        token = None
        for _ in range(20):
            output = await asyncio.to_thread(
                self.client("rekognition").get_label_detection,
                JobId=job_id,
                MaxResults=1000,
                **({"NextToken": token} if token else {}),
            )
            if output["JobStatus"] == "FAILED":
                return ProviderResult("failed", job_id, error="provider_failed")
            if output["JobStatus"] != "SUCCEEDED":
                return ProviderResult("running", job_id)
            labels.extend(
                {
                    "name": x["Label"]["Name"],
                    "confidence": x["Label"]["Confidence"],
                    "timestamp_ms": x["Timestamp"],
                }
                for x in output.get("Labels", [])
            )
            token = output.get("NextToken")
            if not token:
                break
        require(not token, "provider_result_too_large", "Provider labels exceed bounded result size")
        return ProviderResult("succeeded", job_id, result={"labels": labels})

    async def reconcile(self, run_id, operation, section, request):
        # Transcribe names and Rekognition ClientRequestToken are deterministic.
        if operation == "audio.transcribe":
            try:
                return await self.poll(run_id, operation, "pms-" + str(run_id))
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") == "BadRequestException":
                    return ProviderResult("unknown", error="submission_unknown")
                raise
        # A deterministic start token cannot tell whether the first call reached AWS.
        # Discovery must not create a fresh job after cancellation or permission changes.
        if operation == "video.labels":
            return ProviderResult("unknown", error="operator_reconciliation_required")
        return ProviderResult("unknown", error="submission_unknown")

    async def cleanup(self, run_id, operation, request, job_id):
        if operation == "audio.synthesize":
            return
        if operation == "audio.transcribe":
            try:
                await asyncio.to_thread(
                    self.client("transcribe").delete_transcription_job,
                    TranscriptionJobName=job_id or "pms-" + str(run_id),
                )
            except Exception as error:
                if getattr(error, "response", {}).get("Error", {}).get("Code") != "BadRequestException":
                    raise
        client = self.client("s3")
        bucket = self.config["staging_bucket"]
        await asyncio.to_thread(
            client.delete_object, Bucket=bucket, Key=self.input_key(run_id, request["format"])
        )
        if operation == "audio.transcribe":
            await asyncio.to_thread(client.delete_object, Bucket=bucket, Key=self.output_key(run_id))


class AzureProvider:
    def __init__(self, settings, connection, credentials):
        self.settings = settings
        self.config = copy.deepcopy(connection.settings)
        self.kind = connection.connection_type
        self.auth = connection.auth_mode
        self.credentials = credentials

    async def bearer(self, scope):
        from azure.identity import ClientSecretCredential, DefaultAzureCredential

        identity = (
            ClientSecretCredential(
                self.config["tenant_id"], self.config["client_id"], self.credentials["client_secret"]
            )
            if self.auth == "service_principal"
            else DefaultAzureCredential()
        )
        try:
            return (await asyncio.to_thread(identity.get_token, scope)).token
        finally:
            await asyncio.to_thread(identity.close)

    async def speech_headers(self, tts=False):
        if self.auth == "api_key":
            return {"Ocp-Apim-Subscription-Key": self.credentials["api_key"]}
        token = await self.bearer("https://cognitiveservices.azure.com/.default")
        if tts:
            resource_id = self.config.get("resource_id")
            require(
                bool(resource_id),
                "resource_id_required",
                "Speech resource ID is required for Entra text-to-speech",
            )
            token = f"aad#{resource_id}#{token}"
        return {"Authorization": "Bearer " + token}

    def speech_url(self, operation):
        endpoint = self.config.get("endpoint")
        if endpoint:
            path = {
                "voices": "/tts/cognitiveservices/voices/list",
                "synthesize": "/tts/cognitiveservices/v1",
                "transcribe": "/speechtotext/transcriptions:transcribe",
            }[operation]
            return endpoint.rstrip("/") + path
        if operation == "transcribe":
            return f"https://{self.config['region']}.api.cognitive.microsoft.com/speechtotext/transcriptions:transcribe"
        return f"https://{self.config['region']}.tts.speech.microsoft.com/cognitiveservices/" + (
            "voices/list" if operation == "voices" else "v1"
        )

    async def vi_token(self):
        c = self.config
        url = f"https://management.azure.com/subscriptions/{quote(c['subscription_id'], safe='')}/resourceGroups/{quote(c['resource_group'], safe='')}/providers/Microsoft.VideoIndexer/accounts/{quote(c['account_name'], safe='')}/generateAccessToken"
        async with httpx.AsyncClient(
            timeout=self.settings.provider_timeout_seconds, follow_redirects=False
        ) as client:
            result = await client.post(
                url,
                params={"api-version": "2025-04-01"},
                headers={
                    "Authorization": "Bearer " + await self.bearer("https://management.azure.com/.default")
                },
                json={"permissionType": "Contributor", "scope": "Account"},
            )
            result.raise_for_status()
            return result.json()["accessToken"]

    def vi_url(self, suffix=""):
        return f"https://api.videoindexer.ai/{quote(self.config['location'], safe='')}/Accounts/{quote(self.config['account_id'], safe='')}/{suffix}"

    async def validate(self, operation, sample=False):
        require(not sample, "sample_via_run", "Use a bounded processing run for an end-to-end sample test")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            if self.kind == "azure_video_indexer":
                result = await client.get(
                    self.vi_url("Videos"), params={"accessToken": await self.vi_token(), "pageSize": 1}
                )
            elif operation == "audio.transcribe":
                result = await client.get(
                    self.speech_url("transcribe").removesuffix("transcriptions:transcribe")
                    + "transcriptions/locales",
                    params={"api-version": "2024-11-15"},
                    headers=await self.speech_headers(),
                )
            else:
                result = await client.get(
                    self.speech_url("voices"),
                    headers=await self.speech_headers(tts=True),
                )
            result.raise_for_status()
        return True

    async def stage(self, run_id, data, extension):
        return None

    async def submit(self, run_id, operation, section, request, data=None):
        async with httpx.AsyncClient(
            timeout=self.settings.provider_timeout_seconds, follow_redirects=False
        ) as client:
            if operation == "audio.synthesize":
                options = synthesis_parameters("azure_speech", section, request)
                language, voice = options["language"], options["voice"]
                ssml = f'<speak version="1.0" xml:lang="{escape(language, {chr(34): "&quot;"})}"><voice name="{escape(voice, {chr(34): "&quot;"})}">{escape(request["text"])}</voice></speak>'
                output_format = {
                    "mp3": "audio-24khz-48kbitrate-mono-mp3",
                    "wav": "riff-24khz-16bit-mono-pcm",
                    "pcm": "raw-24khz-16bit-mono-pcm",
                }.get(section.get("format") or "mp3")
                require(
                    output_format is not None, "unsupported_format", "Azure synthesis format is unsupported"
                )
                result = await client.post(
                    self.speech_url("synthesize"),
                    headers={
                        **await self.speech_headers(tts=True),
                        "Content-Type": "application/ssml+xml",
                        "X-Microsoft-OutputFormat": output_format,
                        "User-Agent": "pms-api",
                    },
                    content=ssml,
                )
                result.raise_for_status()
                return ProviderResult(
                    "succeeded", result={"format": section.get("format") or "mp3"}, audio=result.content
                )
            if operation == "audio.transcribe":
                result = await client.post(
                    self.speech_url("transcribe"),
                    params={"api-version": "2024-11-15"},
                    headers=await self.speech_headers(),
                    files={"audio": ("input." + request["format"], data)},
                    data={"definition": json.dumps({"locales": [section.get("language") or "en-US"]})},
                )
                result.raise_for_status()
                value = result.json()
                return ProviderResult(
                    "succeeded",
                    result={"text": " ".join(p.get("text", "") for p in value.get("combinedPhrases", []))},
                )
            token = await self.vi_token()
            result = await client.post(
                self.vi_url("Videos"),
                params={
                    "accessToken": token,
                    "name": "pms-" + str(run_id),
                    "externalId": str(run_id),
                    "privacy": "Private",
                    "indexingPreset": "VideoOnly",
                },
                files={"file": ("input.mp4", data, "video/mp4")},
            )
            result.raise_for_status()
            return ProviderResult("running", job_id=result.json()["id"])

    async def poll(self, run_id, operation, job_id):
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(
                self.vi_url("Videos/" + quote(job_id, safe="") + "/Index"),
                params={"accessToken": await self.vi_token()},
            )
            response.raise_for_status()
            value = response.json()
        if value.get("state") == "Failed":
            return ProviderResult("failed", job_id, error="provider_failed")
        if value.get("state") != "Processed":
            return ProviderResult("running", job_id)
        labels: list[dict] = []
        for video in value.get("videos", []):
            for label in video.get("insights", {}).get("labels", []):
                labels.append({"name": label.get("name"), "instances": label.get("instances", [])})
        return ProviderResult("succeeded", job_id, result={"labels": labels})

    async def reconcile(self, run_id, operation, section, request):
        if operation != "video.labels":
            return ProviderResult("unknown", error="submission_unknown")
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            response = await client.get(
                self.vi_url("Videos/Search"),
                params={"accessToken": await self.vi_token(), "externalId": str(run_id)},
            )
            response.raise_for_status()
            results = response.json().get("results", [])
        if len(results) == 1:
            return await self.poll(run_id, operation, results[0]["id"])
        return ProviderResult("unknown", error="submission_unknown")

    async def cleanup(self, run_id, operation, request, job_id):
        if operation != "video.labels":
            return
        require(bool(job_id), "submission_unknown", "Reconcile the Video Indexer job before cleanup", 409)
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            result = await client.delete(
                self.vi_url("Videos/" + quote(job_id, safe="")), params={"accessToken": await self.vi_token()}
            )
            if result.status_code != 404:
                result.raise_for_status()


class ProviderFactory:
    def __init__(self, settings):
        self.settings = settings

    def for_connection(self, connection):
        require(
            self.settings.external_calls_enabled,
            "external_calls_disabled",
            "External provider calls are disabled by deployment configuration",
            503,
        )
        require(
            connection.auth_mode not in {"api_key", "access_key", "service_principal"}
            or connection.encrypted_credentials,
            "credentials_migration_required",
            "Replace legacy secret references with encrypted credentials",
            409,
        )
        credentials = CredentialVault(self.settings).decrypt(connection)
        if connection.connection_type == "azure_openai_whisper":
            from pms_api.integrations.whisper_cloud import AzureWhisperProvider

            return AzureWhisperProvider(self.settings, connection, credentials)
        return (AWSProvider if connection.provider == "aws" else AzureProvider)(
            self.settings, connection, credentials
        )
