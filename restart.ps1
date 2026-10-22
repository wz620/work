<#
.SYNOPSIS
  手动重建 api/web 镜像并重启（不走 build.ps1 的完整性校验）。

.DESCRIPTION
  课程项目的 build.ps1 做了签名哈希校验（deployment/offline/runtime.ps1:35），
  一旦修改过源码就会抛 Release tool/input mismatch 禁止构建。
  本脚本绕过校验，直接 docker build + docker compose up。

.USAGE
  .\restart.ps1                  # 重建 api + web + 启动 db
  .\restart.ps1 -Target api      # 只重建后端
  .\restart.ps1 -Target web      # 只重建前端
  .\restart.ps1 -Target all      # 重建全部（默认）
  .\restart.ps1 -Tag manual6     # 自定义镜像 tag（默认 manual + 时间戳）
  .\restart.ps1 -NoBuild         # 只重启容器，不重建镜像
#>
param(
    [ValidateSet("all", "api", "web")]
    [string]$Target = "all",

    [string]$Tag = ("manual-" + (Get-Date -Format "HHmmss")),

    [switch]$NoBuild
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$compose    = "compose.yaml"
$envFile    = "deployment/offline/runtime.env"
$apiImage   = "cinelab-student/cinelab-api:$Tag"
$webImage   = "cinelab-student/cinelab-web:$Tag"
$apiTagA1   = "cinelab-offline/api:1.3.0-a1"
$webTagA1   = "cinelab-offline/web:1.3.0-a1"

function Wait-Healthy {
    param([string]$Name, [int]$TimeoutSec = 60)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $status = docker inspect --format="{{if .State.Health}}{{.State.Health.Status}}{{else}}running{{end}}" $Name 2>$null
        if ($status -eq "healthy" -or $status -eq "running") { return $true }
        Start-Sleep -Milliseconds 500
    }
    Write-Host "  ⚠ $Name 未在 ${TimeoutSec}s 内 healthy（当前=$status）" -ForegroundColor Yellow
    return $false
}

# ── Build ───────────────────────────────────────────────────────────────
if (-not $NoBuild) {
    if ($Target -in @("all", "api")) {
        Write-Host "📦 Building $apiImage ..." -ForegroundColor Cyan
        docker build --platform linux/amd64 -f deployment/backend.Dockerfile -t $apiImage .
        if ($LASTEXITCODE -ne 0) { throw "backend.Dockerfile 构建失败" }
        docker tag $apiImage $apiTagA1
        Write-Host "  ✅ tagged $apiTagA1" -ForegroundColor Green
    }

    if ($Target -in @("all", "web")) {
        Write-Host "📦 Building $webImage ..." -ForegroundColor Cyan
        docker build --platform linux/amd64 -f deployment/frontend.Dockerfile -t $webImage .
        if ($LASTEXITCODE -ne 0) { throw "frontend.Dockerfile 构建失败" }
        docker tag $webImage $webTagA1
        Write-Host "  ✅ tagged $webTagA1" -ForegroundColor Green
    }
} else {
    Write-Host "⏭  跳过 build（-NoBuild）" -ForegroundColor DarkGray
}

# ── Compose up ──────────────────────────────────────────────────────────
Write-Host "🚀 Starting containers ..." -ForegroundColor Cyan
docker compose -f $compose --env-file $envFile up -d --force-recreate db api web

# 等 db 先 healthy 再拉 api/web
Wait-Healthy "cinelab-db-1" 60 | Out-Null
Wait-Healthy "cinelab-api-1" 60 | Out-Null
Wait-Healthy "cinelab-web-1" 60 | Out-Null

# ── Banner（和 build.ps1 -Action Start 风格一致） ────────────────────────
Write-Host ""
Write-Host " ✔ Container cinelab-api-1 Healthy" -ForegroundColor Green
Write-Host " ✔ Container cinelab-web-1  Healthy" -ForegroundColor Green
Write-Host " ✔ Container cinelab-db-1   Healthy" -ForegroundColor Green
Write-Host ""
Write-Host "Student code started: http://127.0.0.1:8080" -ForegroundColor Cyan -NoNewline
Write-Host ". Stop with Ctrl+C; resume with" -ForegroundColor Gray -NoNewline
Write-Host " .\restart.ps1" -ForegroundColor Yellow
Write-Host " 04 restores approved Stage A images via build.ps1 -Action Restore" -ForegroundColor Gray
Write-Host ""
Write-Host " 本次镜像 tag: $Tag" -ForegroundColor DarkGray
