# Script de deploy automatizado para a VPS Oracle (147.15.18.148)
$ErrorActionPreference = "Stop"

$User = "ubuntu"
$Host_ = "147.15.18.148"
$RemoteDir = "/home/ubuntu/apps/api-notebooklm"
$KeyPath = Join-Path $env:USERPROFILE ".ssh\oracle-vps.key"

if (-not (Test-Path $KeyPath)) {
    Write-Error "Chave SSH nao encontrada em $KeyPath"
    exit 1
}

Write-Host "Criando estrutura de pastas remota em $RemoteDir..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "mkdir -p $RemoteDir/app $RemoteDir/data/auth $RemoteDir/storage"

Write-Host "Empacotando e sincronizando arquivos do projeto via SSH..." -ForegroundColor Cyan
$ProjectDir = $PSScriptRoot

# Compacta e envia os arquivos necessarios diretamente pelo SSH
tar -czf - -C "$ProjectDir" app main.py Dockerfile docker-compose.yml requirements.txt | `
    ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "tar -xzf - -C $RemoteDir"

# Envia o arquivo .env se ele existir localmente
if (Test-Path "$ProjectDir\.env") {
    Write-Host "Enviando arquivo .env..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$ProjectDir\.env" "$User@$Host_:$RemoteDir/.env"
}

# Envia o master_token.json se existir localmente em data/auth/
$LocalMasterToken = "$ProjectDir\data\auth\master_token.json"
if (Test-Path $LocalMasterToken) {
    Write-Host "Enviando credencial master_token.json..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=accept-new "$LocalMasterToken" "$User@$Host_:$RemoteDir/data/auth/master_token.json"
}

Write-Host "Construindo imagem e subindo container na VPS..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "cd $RemoteDir && docker compose up -d --build"

Write-Host "Verificando status do container..." -ForegroundColor Cyan
ssh -i $KeyPath -o StrictHostKeyChecking=accept-new "$User@$Host_" "docker ps --filter name=api-notebooklm"

Write-Host ""
Write-Host "Deploy concluido com sucesso." -ForegroundColor Green
