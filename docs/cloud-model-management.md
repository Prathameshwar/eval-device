# Cloud model management

Models are managed by platform administrators in `/models`. Each model owns its provider settings and encrypted credentials. Device selections refer directly to these model records. Tenant permissions and provider/deployment gates still apply when executing requests.

| Type | Supported cloud providers | Required configuration |
| --- | --- | --- |
| Conversation | OpenAI, Azure OpenAI, Anthropic, OpenAI-compatible | Allowed API base URL, model ID (Azure: deployment name), API key; optional reply limit and protocol options |
| Speech recognition | Azure OpenAI Whisper | Allowed Azure `/openai/v1` endpoint, deployment name, API key; optional file API version or Realtime Whisper |
| Speech recognition | Amazon Transcribe | AWS region, private staging bucket, access keys/server identity/assumed role |
| Speech recognition | Azure Speech | Region and API key, or resource endpoint/resource ID with server/application identity |
| Speech output | Amazon Polly | Region and AWS authentication; optional language, voice and audio format |
| Speech output | Azure Speech | Region and Azure authentication; optional resource endpoint, language, voice and audio format |
| Video | Amazon Rekognition | Region, private staging bucket and AWS authentication |
| Video | Azure Video Indexer | Subscription, resource group, account name/ID, region and server/application identity |

AWS temporary credentials include an optional session token. Transcribe/Rekognition may use a custom staging prefix. Azure Speech resource endpoints are optional with API keys and required with identity authentication. Whisper language preferences are `en`, `hi` or `auto`; other speech providers use locales such as `en-IN` or `hi-IN`.

Conversation reply limits are 16-4096 tokens. The optional compatibility controls choose the output-token parameter, streaming usage request, and instruction role for OpenAI-protocol deployments. Existing model capability settings are preserved when editing. Anthropic uses its native Messages API. Provider/model support must match the configured deployment.

Save before selecting **Test connection**. `POST /api/v1/platform/runtime-models/{id}/test` accepts `expected_revision`. It checks the saved cloud model, requires an active platform administrator, and rechecks authentication, provider availability and the model revision after provider I/O. It has a 30-second deadline and records a redacted audit result without changing the model or device configuration. Inactive, archived, local, stale and unauthorized models cannot be tested through this endpoint.

The test checks model catalog/API access for conversation and Whisper, service access for media, and temporary staging write/read/delete access for AWS input processing. It does not submit an inference job or use tenant media. A passing result always returns `inference_verified: false`: it does not prove an Azure deployment name, chosen voice, inference permission, quota, media format, or hardware execution works. Execute a bounded device request to verify those with a real provider account. Unknown inference submissions are never automatically replayed.

Creating and assigning a model does not enable external calls. The operator must configure allowed LLM/Whisper URLs and enable external calls; AWS/Azure also require their provider enabled in Platform options. Credentials remain encrypted in PostgreSQL and are never returned. Blank credentials on edit retain the saved key; changing the endpoint or keyed authentication requires fresh credentials. Switching to server identity clears stored keys. Models assigned to non-retired devices cannot be deleted.

Conversation requests use the LLM APIs. Interactive Whisper uses the speech API. Amazon Transcribe, Azure Speech, Polly, Rekognition and Video Indexer use processing runs and the worker. These paths are distinct; an available model is not a guarantee that every client implements every processing operation.

Provider contract references used in the review: [Azure Speech REST](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech), [Azure Speech custom endpoints](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-services-private-link), [Microsoft custom endpoint synthesis example](https://microsoft-foundry.github.io/forgebook/notebook/mai-voice-1-foundry/), [fast transcription](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/fast-transcription-create), and [Amazon Polly synthesis](https://docs.aws.amazon.com/polly/latest/APIReference/API_SynthesizeSpeech.html).

Verification on 2026-10-04 used mocked provider calls and disposable PostgreSQL. No live provider, deployed cloud, or hardware execution is claimed. See [review evidence](pms-api-reviews.md).

Device configuration also reports whether the device, tenant and department currently allow changes. A disabled cloud speech-recognition assignment remains disabled without blocking the independently selected conversation model. Clearing all slots disables those operations for that device; a tenant transfer retains the physical device ID and starts with empty model assignments.
