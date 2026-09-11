# Script de deploy automatizado para a VPS Oracle (147.15.18.148)
$ErrorActionPreference = "Stop"

$User = "ubuntu"
$Host_ = "147.15.18.148"
$RemoteDir = "/home/ubuntu/apps/api-notebooklm"
$KeyPath = Join-Path $env:USERPROFILE ".ssh\oracle-vps.key"

if (-not (Test-Path $KeyPath)) {
    Write-Error "Chave SSH não encontrada em $KeyPath"
    exit 1
}

Write-Host "Criando estrutura de pastas remota em $RemoteDir..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "mkdir -p $RemoteDir/app $RemoteDir/data/auth $RemoteDir/storage && chmod 700 $RemoteDir/data/auth"

Write-Host "Empacotando e sincronizando arquivos do projeto via SSH..." -ForegroundColor Cyan
$ProjectDir = $PSScriptRoot
$TarFile = Join-Path $env:TEMP "deploy-api-notebooklm.tar.gz"

try {
    tar -czf "$TarFile" -C "$ProjectDir" app main.py Dockerfile docker-compose.yml requirements.txt
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$TarFile" "${User}@${Host_}:/tmp/deploy-api-notebooklm.tar.gz"
    ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "tar -xzf /tmp/deploy-api-notebooklm.tar.gz -C $RemoteDir && rm -f /tmp/deploy-api-notebooklm.tar.gz"
} finally {
    if (Test-Path "$TarFile") {
        Remove-Item -Force "$TarFile"
    }
}

# Envia o arquivo .env se ele existir localmente
if (Test-Path "$ProjectDir\.env") {
    Write-Host "Enviando arquivo .env..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$ProjectDir\.env" "${User}@${Host_}:${RemoteDir}/.env"
}

# Envia o master_token.json se existir localmente em data/auth/
$LocalMasterToken = "$ProjectDir\data\auth\master_token.json"
if (Test-Path $LocalMasterToken) {
    Write-Host "Enviando credencial master_token.json..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$LocalMasterToken" "${User}@${Host_}:${RemoteDir}/data/auth/master_token.json"
}

# Envia o storage_state.json se existir localmente em data/auth/
$LocalStorageState = "$ProjectDir\data\auth\storage_state.json"
if (Test-Path $LocalStorageState) {
    Write-Host "Enviando sessão inicial storage_state.json..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$LocalStorageState" "${User}@${Host_}:${RemoteDir}/data/auth/storage_state.json"
}

Write-Host "Ajustando permissões de segurança nos arquivos de credenciais..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "chmod 600 $RemoteDir/data/auth/* $RemoteDir/.env 2>/dev/null || true"

Write-Host "Construindo imagem e subindo container na VPS..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "cd $RemoteDir && docker compose up -d --build"

Write-Host "Verificando status do container..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "docker ps --filter name=api-notebooklm"

Write-Host ""
Write-Host "Deploy concluído com sucesso." -ForegroundColor Green
