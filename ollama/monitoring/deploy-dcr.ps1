#Requires -Modules Az.Resources, Az.ConnectedMachine
<#
.SYNOPSIS
    Deploys the Data Collection Rule and installs Azure Monitor Agent on the
    Arc-connected home LLM server. Run from your Windows PC after the Linux
    server has been onboarded via monitoring/onboard-arc.sh.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $SubscriptionId,
    [Parameter(Mandatory)] [string] $ResourceGroupName,
    [Parameter(Mandatory)] [string] $WorkspaceName,
    [Parameter(Mandatory)] [string] $ArcMachineName,
    [string] $Location       = "australiaeast",
    [string] $DcrName        = "dcr-home-llm-server"
)

$ErrorActionPreference = "Stop"

# ── Login ─────────────────────────────────────────────────────────────────────
Write-Host "`n==> Connecting to Azure" -ForegroundColor Cyan
Connect-AzAccount -Subscription $SubscriptionId | Out-Null
Set-AzContext -SubscriptionId $SubscriptionId | Out-Null
Write-Host "    OK: Connected to subscription $SubscriptionId" -ForegroundColor Green

# ── Resolve resource IDs ──────────────────────────────────────────────────────
Write-Host "`n==> Resolving resource IDs" -ForegroundColor Cyan

$workspace = Get-AzOperationalInsightsWorkspace `
    -ResourceGroupName $ResourceGroupName `
    -Name $WorkspaceName
$workspaceId = $workspace.ResourceId
Write-Host "    Workspace : $workspaceId" -ForegroundColor DarkGray

$arcMachine = Get-AzConnectedMachine `
    -ResourceGroupName $ResourceGroupName `
    -Name $ArcMachineName
$arcMachineId = $arcMachine.Id
Write-Host "    Arc machine: $arcMachineId" -ForegroundColor DarkGray

# ── Deploy ARM template ────────────────────────────────────────────────────────
Write-Host "`n==> Deploying DCR + AMA extension" -ForegroundColor Cyan
$templateFile = Join-Path $PSScriptRoot "dcr-template.json"

$deployment = New-AzResourceGroupDeployment `
    -ResourceGroupName  $ResourceGroupName `
    -TemplateFile       $templateFile `
    -dcrName            $DcrName `
    -location           $Location `
    -workspaceResourceId $workspaceId `
    -arcMachineResourceId $arcMachineId `
    -Verbose

if ($deployment.ProvisioningState -eq "Succeeded") {
    Write-Host "    OK: Deployment succeeded" -ForegroundColor Green
    Write-Host "    DCR resource ID: $($deployment.Outputs['dcrResourceId'].Value)" -ForegroundColor DarkGray
} else {
    Write-Error "Deployment finished with state: $($deployment.ProvisioningState)"
}

# ── Done ──────────────────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Monitoring deployment complete" -ForegroundColor Green
Write-Host ""
Write-Host "  Logs will appear in Sentinel within ~5 minutes." -ForegroundColor White
Write-Host "  Table: Syslog" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Useful KQL to verify data is flowing:" -ForegroundColor White
Write-Host '  Syslog | where Computer == "$ArcMachineName" | take 20' -ForegroundColor DarkGray
Write-Host "==========================================" -ForegroundColor Green
