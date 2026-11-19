"""校验 GitHub 仓库中的文件清单与内容一致性。"""
import base64
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, token, retries=6):
    """本机 TLS 握手不稳定（Errno 0 / SYSCALL），必须重试。"""
    last = None
    for i in range(retries):
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": "Bearer %s" % token,
                "Accept": "application/vnd.github+json",
                "User-Agent": "verify-script",
            },
        )
        try:
            with opener.open(req, timeout=90) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            last = e
            time.sleep(2 * (i + 1))
    raise last


def main():
    repo_dir, slug, branch, token = sys.argv[1:5]
    base = "https://api.github.com/repos/%s/contents" % slug
    tree = get("%s?ref=%s" % (base, branch), token)

    remote = {}
    for it in tree:
        remote[it["path"]] = it
        if it["type"] == "dir":
            for sub in get("%s/%s?ref=%s" % (base, it["path"], branch), token):
                remote[sub["path"]] = sub

    local = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d != ".git"]
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, repo_dir).replace("\\", "/")
            local.append((rel, full))

    print("REMOTE_FILES=%d LOCAL_FILES=%d" % (len(remote), len(local)))
    print("%-38s %10s %10s %s" % ("path", "local", "remote", "match"))
    print("-" * 72)
    all_ok = True
    for rel, full in sorted(local):
        size = os.path.getsize(full)
        r = remote.get(rel)
        if not r:
            print("%-38s %10d %10s %s" % (rel, size, "-", "MISSING"))
            all_ok = False
            continue
        # 逐字节一致校验
        blob = get("%s/%s?ref=%s" % (base, rel, branch), token)
        content = base64.b64decode(blob["content"])
        with open(full, "rb") as f:
            raw = f.read()
        same = hashlib.sha256(content).hexdigest() == hashlib.sha256(raw).hexdigest()
        print("%-38s %10d %10d %s" % (rel, size, r["size"], "OK" if same else "DIFF"))
        if not same:
            all_ok = False

    extra = set(remote) - set(x[0] for x in local)
    if extra:
        print("REMOTE_ONLY: %s" % ", ".join(sorted(extra)))
    print("---")
    print("RESULT=%s" % ("ALL_MATCH" if all_ok else "MISMATCH"))
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
