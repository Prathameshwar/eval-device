/** Display labels for the fixed provider catalog the API exposes at `GET /providers`. */
export const PROVIDER_LABELS: Record<string, string> = {
  openai: 'OpenAI Cloud',
  azure_openai: 'Azure OpenAI',
  openai_compatible: 'OpenAI-Compatible Endpoint',
  local_llama_cpp: 'Local Llama.cpp',
  azure: 'Azure Cognitive Services',
  aws: 'AWS',
  anthropic: 'Anthropic',
  google: 'Google Gemini',
  aws_bedrock: 'AWS Bedrock',
};
