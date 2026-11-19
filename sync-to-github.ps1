<#
.SYNOPSIS
    把 source/hangzhou-3day-guide.html 同步到 GitHub（自动更新 index.html）。

.DESCRIPTION
    流程：源文件 -> index.html -> 语法校验 -> 增量上传 -> 输出线上地址。

    为什么不用 git push：
    本机常年挂着 127.0.0.1:1832 的本地代理，对 github.com 会导致 TLS 握手直接中断
    （SSL_ERROR_SYSCALL），git push 反复失败。因此改走 GitHub Contents API，
    并在脚本里显式禁用代理。

    - 单一真源是 source/hangzhou-3day-guide.html，index.html 是自动生成的副本。
    - 认证用 gh auth token 动态取值，不落盘、不写进任何配置。
    - 只上传内容有变化的文件，未变的自动跳过。

.PARAMETER Message
    自定义提交信息。默认带时间戳。

.PARAMETER DryRun
    只显示将要更新哪些文件，不实际推送。

.EXAMPLE
    .\sync-to-github.ps1

.EXAMPLE
    .\sync-to-github.ps1 -Message "调整周六晚间演出顺序"

.EXAMPLE
    .\sync-to-github.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [string]$Message = "",
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoDir    = $PSScriptRoot
$SourceFile = Join-Path $RepoDir "source\hangzhou-3day-guide.html"
$IndexFile  = Join-Path $RepoDir "index.html"
$Uploader   = Join-Path $RepoDir "tools\gh_upload.py"
$RepoSlug   = "kbybbb806/hangzhou-zzz-trip"
$PagesUrl   = "https://kbybbb806.github.io/hangzhou-zzz-trip/"

function Write-Step($t) { Write-Host "==> $t" -ForegroundColor Cyan }
function Write-Ok($t)   { Write-Host "    $t" -ForegroundColor Green }
function Write-Warn($t) { Write-Host "    $t" -ForegroundColor Yellow }

# ---------- 0. 环境 ----------
# 清空代理变量，否则 GitHub 的 TLS 握手会中断
$env:HTTP_PROXY = ""
$env:HTTPS_PROXY = ""
$env:ALL_PROXY = ""
$env:http_proxy = ""
$env:https_proxy = ""
$env:no_proxy = "*"

# 控制台按 UTF-8 输出，否则 python 打印的中文会显示成乱码
try { [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false) } catch { }

if (-not (Test-Path $SourceFile)) { throw "找不到源文件：$SourceFile" }
if (-not (Test-Path $Uploader))   { throw "找不到上传工具：$Uploader" }

# 找 python
$py = $null
foreach ($p in @(
    "C:\ProgramData\Anaconda3\python.exe",
    "$env:USERPROFILE\.workbuddy\binaries\python\envs\default\Scripts\python.exe",
    "$env:USERPROFILE\.workbuddy\binaries\python\versions\3.13.12\python.exe"
)) { if (Test-Path $p) { $py = $p; break } }
if (-not $py) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) { throw "找不到 python，请安装 Python 3 或修改本脚本的路径列表" }
Write-Ok "python: $py"

# ---------- 1. 源文件 -> index.html ----------
Write-Step "同步源文件 -> index.html"
$srcHash = (Get-FileHash $SourceFile -Algorithm SHA256).Hash
$idxHash = if (Test-Path $IndexFile) { (Get-FileHash $IndexFile -Algorithm SHA256).Hash } else { "" }
if ($srcHash -ne $idxHash) {
    Copy-Item $SourceFile -Destination $IndexFile -Force
    Write-Ok "index.html 已更新"
} else {
    Write-Ok "index.html 已是最新"
}

# ---------- 2. 语法校验 ----------
$node = $null
foreach ($p in @(
    "$env:USERPROFILE\.workbuddy\binaries\node\versions\22.22.2-3\node.exe",
    "C:\Program Files\nodejs\node.exe"
)) { if (Test-Path $p) { $node = $p; break } }

if ($node) {
    Write-Step "校验内联 JS 语法"
    $html = [System.IO.File]::ReadAllText($IndexFile, (New-Object System.Text.UTF8Encoding($false)))
    $blocks = [regex]::Matches($html, '(?s)<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>')
    $tmpJs = Join-Path $env:TEMP ("sync_check_{0}.js" -f $PID)
    ($blocks | ForEach-Object { $_.Groups[1].Value }) -join "`n;`n" |
        Set-Content $tmpJs -Encoding UTF8
    $out = & $node --check $tmpJs 2>&1
    $rc = $LASTEXITCODE
    Remove-Item $tmpJs -Force -ErrorAction SilentlyContinue
    if ($rc -ne 0) {
        Write-Warn "语法校验未通过，已中止（避免把坏页面推上线）："
        $out | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
        exit 1
    }
    Write-Ok "语法 OK（$($blocks.Count) 个内联脚本块）"
} else {
    Write-Warn "未找到 node，跳过语法校验"
}

# ---------- 3. 校验 token ----------
Write-Step "校验 GitHub 认证"
$token = ""
try { $token = (& gh auth token 2>&1 | Out-String).Trim() } catch { }
if (-not $token -or $token.Length -lt 20) {
    throw "取不到 gh token，请先执行：gh auth login"
}
$env:GH_TOKEN = $token
Write-Ok "已认证（token 长度 $($token.Length)）"

# ---------- 4. 上传 ----------
if (-not $Message) {
    $Message = "更新行程攻略 " + (Get-Date -Format "yyyy-MM-dd HH:mm")
}

Write-Step "上传到 GitHub（只传有变化的文件）"
$uploadArgs = @($Uploader, $RepoDir, $RepoSlug, "main", $Message)
if ($DryRun) { $uploadArgs += "--dry-run" }

& $py @uploadArgs
$rc = $LASTEXITCODE

Write-Host ""
if ($rc -ne 0) {
    Write-Warn "上传未完成，部分文件失败。重跑本脚本即可续传（已成功的会自动跳过）。"
    exit 1
}
if ($DryRun) {
    Write-Warn "DRY-RUN 结束，未实际推送。"
    exit 0
}

Write-Host "  同步完成" -ForegroundColor Green
Write-Host "  仓库: https://github.com/$RepoSlug" -ForegroundColor Gray
Write-Host "  页面: $PagesUrl" -ForegroundColor Gray
Write-Host "  （Pages 约 1 分钟后自动更新，强制刷新 Ctrl+F5 可见新版）" -ForegroundColor DarkGray
