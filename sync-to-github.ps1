<#
.SYNOPSIS
    把 source/hangzhou-3day-guide.html 同步到 GitHub（自动更新 index.html）。

.DESCRIPTION
    流程：复制源文件 -> 暂存 -> 提交 -> 推送。
    - 单一真源在 source/，index.html 是自动生成的副本，不要手改 index.html。
    - 认证用 gh CLI 的动态 token，不写入磁盘、不进 git 配置。
    - 自动清空可能失效的本地代理变量，并带重试。

.PARAMETER Message
    自定义提交信息。默认带时间戳。

.EXAMPLE
    .\sync-to-github.ps1

.EXAMPLE
    .\sync-to-github.ps1 -Message "调整周六晚间演出顺序"
#>
[CmdletBinding()]
param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

$RepoDir  = $PSScriptRoot
$SourceFile = Join-Path $RepoDir "source\hangzhou-3day-guide.html"
$IndexFile  = Join-Path $RepoDir "index.html"
$RepoSlug   = "kbybbb806/hangzhou-zzz-trip"
$PagesUrl   = "https://kbybbb806.github.io/hangzhou-zzz-trip/"

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

# ---------- 0. 环境准备 ----------
# 本机常年挂着 127.0.0.1:1832 的本地代理，它对 GitHub 会导致 TLS 握手中断 / EOF。
# 这里统一清空，避免 push 时莫名其妙失败。
$env:HTTP_PROXY  = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY   = ""
$env:http_proxy  = ""
$env:https_proxy = ""
$env:no_proxy    = "*"
$env:GIT_TERMINAL_PROMPT = "0"

if (-not (Test-Path $SourceFile)) {
    throw "找不到源文件：$SourceFile"
}

# ---------- 1. 同步源文件到 index.html ----------
Write-Step "同步源文件 -> index.html"
$srcHash = (Get-FileHash $SourceFile -Algorithm SHA256).Hash
$idxHash = if (Test-Path $IndexFile) { (Get-FileHash $IndexFile -Algorithm SHA256).Hash } else { "" }

if ($srcHash -ne $idxHash) {
    Copy-Item $SourceFile -Destination $IndexFile -Force
    Write-Ok "已更新 index.html"
} else {
    Write-Ok "index.html 已是最新，无需复制"
}

# ---------- 2. 校验 HTML 内联 JS 语法 ----------
$node = $null
foreach ($p in @(
    "$env:USERPROFILE\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
    "C:\Program Files\nodejs\node.exe"
)) { if (Test-Path $p) { $node = $p; break } }

if ($node) {
    Write-Step "校验内联 JS 语法"
    $html = Get-Content $IndexFile -Raw -Encoding UTF8
    $m = [regex]::Matches($html, '(?s)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>')
    $tmpJs = Join-Path $env:TEMP "sync_check_$PID.js"
    ($m | ForEach-Object { $_.Groups[1].Value }) -join "`n;`n" | Set-Content $tmpJs -Encoding UTF8
    $nodeOut = & $node --check $tmpJs 2>&1
    $rc = $LASTEXITCODE
    Remove-Item $tmpJs -Force -ErrorAction SilentlyContinue
    if ($rc -ne 0) {
        Write-Warn "语法校验未通过，已中止推送："
        $nodeOut | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        exit 1
    }
    Write-Ok "语法 OK（$($m.Count) 个内联脚本块）"
} else {
    Write-Warn "未找到 node，跳过语法校验"
}

# ---------- 3. 提交 ----------
Write-Step "提交改动"
Push-Location $RepoDir
try {
    & git add -A 2>&1 | Out-Null

    $dirty = (& git status --porcelain 2>&1 | Out-String).Trim()
    if (-not $dirty) {
        Write-Ok "没有变化，无需提交"
        return
    }
    Write-Ok "变更文件："
    $dirty -split "`r?`n" | Where-Object { $_ } | ForEach-Object { Write-Host "      $_" }

    if (-not $Message) {
        $Message = "更新行程攻略 " + (Get-Date -Format "yyyy-MM-dd HH:mm")
    }

    # 中文提交信息用文件传递，避免 Windows 下 -m 参数按 ANSI 编码导致乱码
    $msgFile = Join-Path $env:TEMP "sync_msg_$PID.txt"
    $enc = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($msgFile, $Message, $enc)
    & git -c i18n.commitEncoding=UTF-8 commit -F $msgFile 2>&1 | Out-Null
    Remove-Item $msgFile -Force -ErrorAction SilentlyContinue
    if ($LASTEXITCODE -ne 0) { throw "git commit 失败" }
    Write-Ok "已提交：$Message"

    # ---------- 4. 推送（带重试） ----------
    Write-Step "推送到 GitHub"
    $token = (& gh auth token 2>&1 | Out-String).Trim()
    if (-not $token -or $token.Length -lt 20) {
        throw "取不到 gh token，请先跑：gh auth login"
    }

    $ok = $false
    for ($i = 1; $i -le 4; $i++) {
        Write-Ok "第 $i 次尝试..."
        & git -c http.proxy= -c https.proxy= `
              -c "http.extraHeader=Authorization: Bearer $token" `
              push origin HEAD:main 2>&1 | ForEach-Object { Write-Host "      $_" }
        if ($LASTEXITCODE -eq 0) { $ok = $true; break }
        if ($i -lt 4) { Start-Sleep -Seconds (3 * $i) }
    }

    if (-not $ok) {
        Write-Warn "推送失败。常见原因：网络波动，或 token 无 repo 权限。"
        Write-Warn "可稍后重跑本脚本（提交已在本地，不会丢）。"
        exit 1
    }

    Write-Host ""
    Write-Host "  推送成功" -ForegroundColor Green
    Write-Host "  仓库: https://github.com/$RepoSlug" -ForegroundColor Gray
    Write-Host "  页面: $PagesUrl" -ForegroundColor Gray
    Write-Host "  （Pages 约 1 分钟后自动更新）" -ForegroundColor DarkGray
}
finally {
    Pop-Location
}
