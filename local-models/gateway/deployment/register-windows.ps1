param(
    [Parameter(Mandatory=$true)][string]$ManagerPython,
    [Parameter(Mandatory=$true)][string]$ManagerFolder,
    [Parameter(Mandatory=$true)][string]$GatewayExe,
    [Parameter(Mandatory=$true)][string]$GatewayConfig,
    [Parameter(Mandatory=$true)][string]$Certificate,
    [Parameter(Mandatory=$true)][string]$PrivateKey,
    [Parameter(Mandatory=$true)][PSCredential]$Credential
)
$ErrorActionPreference = 'Stop'
foreach ($path in @($ManagerPython, $ManagerFolder, $GatewayExe, $GatewayConfig, $Certificate, $PrivateKey)) {
    if (-not (Test-Path -LiteralPath $path) -or $path.Contains('"')) { throw 'Invalid deployment path' }
}
$taskSettings = New-ScheduledTaskSettingsSet -RestartCount 20 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable
$trigger = New-ScheduledTaskTrigger -AtStartup
$managerAction = New-ScheduledTaskAction -Execute $ManagerPython -WorkingDirectory $ManagerFolder -Argument '-m service.daemon --start-selected llm asr tts'
$gatewayArguments = '--config "{0}" --cert "{1}" --key "{2}"' -f $GatewayConfig, $Certificate, $PrivateKey
$gatewayAction = New-ScheduledTaskAction -Execute $GatewayExe -Argument $gatewayArguments
$password = $Credential.GetNetworkCredential().Password
try {
    Register-ScheduledTask -TaskName 'DeviceLocalModels' -Action $managerAction -Trigger $trigger -Settings $taskSettings -User $Credential.UserName -Password $password -Force | Out-Null
    Register-ScheduledTask -TaskName 'DeviceInferenceGateway' -Action $gatewayAction -Trigger $trigger -Settings $taskSettings -User $Credential.UserName -Password $password -Force | Out-Null
} finally {
    $password = $null
}
Write-Output 'Startup tasks registered. Validate account permissions, TLS and model provisioning before starting.'
