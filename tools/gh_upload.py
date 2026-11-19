"""GitHub Contents API 上传器（纯标准库，带重试与增量跳过）。

本机环境有两个必须规避的坑：
1. HTTP(S)_PROXY 指向 127.0.0.1:1832 的本地代理，对 GitHub 会导致 TLS 握手中断
   （SSL_ERROR_SYSCALL / Errno 0 / EOF），因此显式禁用代理。
2. TLS 握手偶发失败，所有请求必须带重试。

用法:
    python gh_upload.py <repo_dir> <owner/repo> [branch] [commit_message] [--dry-run]

token 从环境变量 GH_TOKEN 读取；未设置时自动调用 `gh auth token`。
"""
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

# 禁用代理：本机代理会让 GitHub 的 TLS 握手直接失败
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

API = "https://api.github.com"


def get_token():
    tok = os.environ.get("GH_TOKEN", "").strip()
    if tok:
        return tok
    try:
        out = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, timeout=30
        )
        tok = (out.stdout or "").strip()
        if tok:
            return tok
    except Exception:
        pass
    raise SystemExit("取不到 token：请设置 GH_TOKEN 或先执行 gh auth login")


def request(method, url, token, payload=None, retries=6):
    """带指数退避重试的请求。返回 (status, json)。404 不重试。"""
    last = None
    for i in range(retries):
        data = None
        headers = {
            "Authorization": "Bearer %s" % token,
            "Accept": "application/vnd.github+json",
            "User-Agent": "hangzhou-zzz-sync",
        }
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with opener.open(req, timeout=120) as resp:
                body = resp.read().decode("utf-8")
                return resp.status, json.loads(body) if body.strip() else {}
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            if e.code == 404:
                return 404, {}
            if e.code in (409, 422):
                return e.code, {"error": body}
            if e.code == 401:
                raise SystemExit("401 未授权：token 失效或无 repo 权限")
            last = "HTTP %d %s" % (e.code, body[:200])
        except Exception as e:
            last = "%s: %s" % (type(e).__name__, e)
        time.sleep(2 * (i + 1))
    return 0, {"error": last}


def git_blob_sha(raw):
    """计算 git blob SHA1，用于判断远端内容是否与本地一致。"""
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(raw))
    h.update(raw)
    return h.hexdigest()


def collect(repo_dir):
    out = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in (".git", ".edgeone", "__pycache__")]
        for name in files:
            if name.endswith((".pyc", ".tmp")) or name.startswith("~$"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, repo_dir).replace("\\", "/")
            out.append((rel, full))
    return sorted(out)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    dry = "--dry-run" in sys.argv
    if len(args) < 2:
        raise SystemExit(__doc__)

    repo_dir, slug = args[0], args[1]
    branch = args[2] if len(args) > 2 else "main"
    message = args[3] if len(args) > 3 else "更新行程攻略 " + time.strftime("%Y-%m-%d %H:%M")

    token = get_token()
    files = collect(repo_dir)
    print("本地文件 %d 个，目标 %s@%s" % (len(files), slug, branch))

    changed, skipped, failed = [], [], []

    for rel, full in files:
        with open(full, "rb") as f:
            raw = f.read()
        url = "%s/repos/%s/contents/%s" % (API, slug, rel)

        code, info = request("GET", "%s?ref=%s" % (url, branch), token)
        remote_sha = info.get("sha") if code == 200 else None

        if remote_sha and remote_sha == git_blob_sha(raw):
            skipped.append(rel)
            continue

        if dry:
            changed.append(rel)
            print("WOULD_UPDATE %-40s %6d bytes" % (rel, len(raw)))
            continue

        payload = {"message": message, "content": base64.b64encode(raw).decode(), "branch": branch}
        if remote_sha:
            payload["sha"] = remote_sha

        code, info = request("PUT", url, token, payload)
        if code in (200, 201):
            changed.append(rel)
            print("UPLOAD %-42s %6d bytes" % (rel, len(raw)))
        else:
            failed.append(rel)
            print("FAIL   %-42s %s" % (rel, str(info)[:160]))

    print("-" * 60)
    print("新增/更新 %d | 未变跳过 %d | 失败 %d" % (len(changed), len(skipped), len(failed)))
    if dry:
        return
    if failed:
        sys.exit(1)
    if not changed:
        print("远端已是最新，无需提交")


if __name__ == "__main__":
    main()
