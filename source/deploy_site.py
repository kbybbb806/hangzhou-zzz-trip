# -*- coding: utf-8 -*-
"""
杭州攻略页面 → 腾讯云轻量服务器 部署脚本
用法：python deploy_site.py config.json
config.json: {"host":"1.2.3.4","port":22,"user":"root","password":"xxx"} 或 {"key_file":"C:/path/key.pem"}
可选: "domain":"xxx.com"  "site_dir":"/var/www/hangzhou"  "listen_port":80
"""
import sys, io, json, os, posixpath

import paramiko

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "deploy_out.txt")
lines = []


def log(s=""):
    lines.append(s)
    io.open(LOG, "w", encoding="utf-8").write("\n".join(lines))


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "server.json")
    cfg = json.load(io.open(cfg_path, encoding="utf-8"))

    host = cfg["host"]
    port = int(cfg.get("port", 22))
    user = cfg["user"]
    domain = (cfg.get("domain") or "").strip()
    site_dir = cfg.get("site_dir", "/var/www/hangzhou")
    listen_port = int(cfg.get("listen_port", 80))
    local_html = cfg.get("local_html") or os.path.join(HERE, "杭州3日游.html")

    log("=== 1. 连接 %s@%s:%d ===" % (user, host, port))
    cli = paramiko.SSHClient()
    cli.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kw = dict(hostname=host, port=port, username=user,
              timeout=20, banner_timeout=20, auth_timeout=20, allow_agent=False, look_for_keys=False)
    if cfg.get("key_file"):
        kw["key_filename"] = cfg["key_file"]
        kw["passphrase"] = cfg.get("passphrase") or None
    else:
        kw["password"] = cfg["password"]
    try:
        cli.connect(**kw)
    except Exception as e:
        log("CONNECT_FAIL: %s: %s" % (type(e).__name__, e))
        return
    log("CONNECT_OK")

    def run(cmd, timeout=120):
        try:
            si, so, se = cli.exec_command(cmd, timeout=timeout, get_pty=False)
            out = so.read().decode("utf-8", "replace")
            err = se.read().decode("utf-8", "replace")
            rc = so.channel.recv_exit_status()
            return rc, out.strip(), err.strip()
        except Exception as e:
            return -1, "", "%s: %s" % (type(e).__name__, e)

    # ---------- 2. 环境探测 ----------
    log("\n=== 2. 系统环境 ===")
    rc, out, _ = run("cat /etc/os-release 2>/dev/null | sed -n '1,3p'; echo '--'; uname -m; echo '--'; id -u; echo '--'; whoami")
    log(out or "(no output)")

    rc, out, _ = run("cat /etc/os-release 2>/dev/null | grep -E '^(ID|VERSION_ID)=' ")
    osinfo = out
    log("\nOS: " + osinfo.replace("\n", " "))

    is_root = None
    rc, out, _ = run("id -u")
    if rc == 0 and out.strip().isdigit():
        is_root = (out.strip() == "0")
    log("IS_ROOT=%s" % is_root)
    SUDO = "" if is_root else "sudo -n "

    # sudo 可用性
    if not is_root:
        rc, out, err = run("sudo -n true 2>&1")
        log("SUDO_NOPASSWD_RC=%d %s" % (rc, (out or err)[:200]))

    # ---------- 3. 端口占用（不碰现有服务） ----------
    log("\n=== 3. 现有服务与端口 ===")
    rc, out, _ = run("(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | head -30")
    log(out or "(no output)")
    rc, out, _ = run("for p in %d 80 443 8080; do c=$(ss -lnt 2>/dev/null | grep -c \":$p \"); echo \"PORT_$p=$c\"; done" % listen_port)
    log(out or "")

    # ---------- 4. Nginx 状态 ----------
    log("\n=== 4. Nginx ===")
    rc, out, _ = run("command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 || echo NGINX_NOT_INSTALLED")
    log(out)
    rc, out, _ = run("systemctl is-active nginx 2>/dev/null || echo no-systemd-nginx")
    log("nginx_active=" + (out or "?"))
    rc, out, _ = run("ls -1 /etc/nginx/conf.d/ 2>/dev/null | head -20; echo '--sites-enabled--'; ls -1 /etc/nginx/sites-enabled/ 2>/dev/null | head -20")
    log(out or "(none)")

    # ---------- 5. 建目录 + 上传 ----------
    log("\n=== 5. 上传文件 ===")
    if not os.path.exists(local_html):
        log("LOCAL_HTML_MISSING: " + local_html)
        return
    size = os.path.getsize(local_html)
    log("local=%s bytes=%d" % (local_html, size))

    rc, out, err = run(SUDO + "mkdir -p %s && echo DIR_OK" % site_dir)
    log("mkdir rc=%d %s %s" % (rc, out, err))

    try:
        tr = cli.get_transport()
        sftp = paramiko.SFTPClient.from_transport(tr)
        tmp = "/tmp/index.html"
        sftp.put(local_html, tmp)
        sftp.close()
        log("sftp put -> " + tmp)
        rc, out, err = run(SUDO + "mv -f %s %s/index.html && ls -l %s/index.html" % (tmp, site_dir, site_dir))
        log("move rc=%d %s %s" % (rc, out, err))
        rc, out, _ = run("md5sum %s/index.html 2>/dev/null | awk '{print $1}'" % site_dir)
        log("remote_md5=" + out)
    except Exception as e:
        log("SFTP_FAIL: %s: %s" % (type(e).__name__, e))

    # 本地 md5
    try:
        import hashlib
        m = hashlib.md5(io.open(local_html, "rb").read()).hexdigest()
        log("local_md5=" + m)
    except Exception as e:
        log("local_md5_err %s" % e)

    log("\n=== 探测完成，等待下一步指令 ===")
    cli.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        lines.append("FATAL: " + repr(e))
        lines.append(traceback.format_exc())
        io.open(LOG, "w", encoding="utf-8").write("\n".join(lines))
