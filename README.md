# 杭州 3 日游 · 绝区零 FES + 西湖晨昏摄影

一份可交互的单文件行程攻略。包含逐时时间轴、腾讯地图路线、拍照机位提示、预算明细。

## 在线访问

**<https://kbybbb806.github.io/hangzhou-zzz-trip/>**

GitHub Pages 托管，链接长期有效，可直接发给同行的人，手机浏览器打开即用。

## 行程概要

| 日期 | 内容 |
|---|---|
| 11/26 周四 | D79 动卧 20:00 长沙 → 11/27 04:05 杭州南（05 车 08 号上铺） |
| 11/27 周五 | 04:15 钟点房补觉 → 06:40 打车 20.8km → 07:10 杭州大会展中心排队 → 08:30 入场 **绝区零 FES** → 19:00-21:30 **ZLIVE 音乐会** → 宿游子假日酒店（东站西广场） |
| 11/28 周六 | 04:45 起床 → **06:35 宝石山日出**（保俶塔+西湖+城隍阁+雷峰塔同框）→ 断桥空景/白堤/北山街 → 10:55 远近客栈办入住 → 12:20 午睡 → **16:58 长桥·雷峰夕照** → 17:20 步行回房 → 18:40 **西子廊桥盲盒音乐会** → 19:30 **西湖音乐喷泉** |
| 11/29 周日 | 04:35 退房 → **05:00 九溪烟树晨雾** → 九溪十八涧→龙井村 → 永福寺/灵隐 → 茅家埠/浴鹄湾 → 白塔公园 → 江洋畈 → 14:40 杭州东站 → **G207 16:44 → 19:59 长沙南** |

- 人数：11/27 单人（FES/ZLIVE），11/28-29 双人
- 总预算：约 ¥3,177（本人约 ¥2,568 + 同伴 ¥609）
- 住宿：11/27 游子假日酒店 ¥105 ｜ 11/28 远近客栈（雷峰塔）¥149 ｜ 11/27 凌晨南站钟点房 ¥67
- 器材：尼康 Z5 + 70-200 f2.8（+2x 增距镜拍 Coser，400mm）+ 24-120 f4 + 影石 Pocket；长曝用**豆袋**替代三脚架

## 仓库结构

```
.
├── index.html                      # 网页入口（自动生成，勿直接编辑）
├── source/
│   ├── hangzhou-3day-guide.html    # 源文件（改这个）
│   └── deploy_site.py              # 可选：部署到自有服务器的 SSH 脚本
├── tools/
│   ├── gh_upload.py                # GitHub Contents API 增量上传器
│   └── gh_verify.py                # 逐字节校验远端与本地一致性
├── vendor/
│   └── leaflet/                    # Leaflet 1.9.4 本地副本（免境外 CDN）
├── sync-to-github.ps1              # 一键同步脚本
├── README.md
└── .nojekyll
```

> 叶子节点引用的 Leaflet 走本地 `vendor/leaflet/`，地图瓦片用高德，均已国内可用。

**单一真源是 `source/hangzhou-3day-guide.html`**。`index.html` 由同步脚本自动复制，不要手动改两处。

## 更新后如何同步

改完 `source/hangzhou-3day-guide.html`，然后：

```powershell
.\sync-to-github.ps1
```

脚本会依次：复制源文件到 `index.html` → 校验内联 JS 语法（不通过就中止，避免把坏页面推上线）→ 增量上传 → 输出线上地址。

常用参数：

```powershell
.\sync-to-github.ps1 -Message "调整周六晚间演出顺序"   # 自定义提交信息
.\sync-to-github.ps1 -DryRun                          # 只看会更新哪些文件，不实际推送
```

推送成功后 Pages 约 1 分钟自动更新，浏览器用 `Ctrl+F5` 强制刷新即可看到新版。

### 只校验不推送

```powershell
$env:GH_TOKEN = (gh auth token)
python tools\gh_verify.py . kbybbb806/hangzhou-zzz-trip main
```

逐文件比对远端内容与本地是否**逐字节一致**（用 git blob SHA1），输出 `ALL_MATCH` 或具体差异。

## 为什么用 API 而不是 git push

本机环境有两个坑，同步脚本都已规避：

1. **本地代理**：`HTTP_PROXY/HTTPS_PROXY` 指向 `127.0.0.1:1832`，经它访问 github.com 会导致 TLS 握手直接中断（`SSL_ERROR_SYSCALL` / `Errno 0` / `EOF`），`git push` 反复失败。脚本统一清空这些变量并显式禁用 urllib 代理。
2. **TLS 抖动**：即使不走代理，握手仍偶发失败，所有请求都带指数退避重试。

因此在没有配置 git credential 的情况下，`git clone/push` 这个仓库可能会失败，**这不影响正常使用**——同步走 API 通道，只有内容有变化的文件才会上传。

认证用 `gh auth token` 动态取值，不落盘、不写进任何配置文件。

## 技术说明

- **零依赖单文件**：HTML + CSS + 内联 JS，不引用外部 CSS/JS（腾讯地图 SDK 按需动态加载）
- **地图三层降级**：腾讯地图 JSAPI GL → Leaflet → 内联静态 SVG。腾讯地图 Key 的域名白名单若不含 `kbybbb806.github.io`，会自动降到第二层；行程卡片、时间轴、预算等全部文字内容不受影响
- **数据驱动渲染**：行程数据集中在 `const dayData = [...]` 与 `const HOTEL_CANDIDATES`，改数据即可，无需动模板
- **富文本白名单**：`richText()` 先整体转义再只放行 `<b>/</b>`，避免 XSS
- **移动端适配**：竖屏单列排版，适合旅途中手机查看

## 备注

页面内的交通耗时、距离来自腾讯位置服务路线规划 API（驾车口径）。凌晨时段实际用时显著短于白天，行程按凌晨路况估算。

## 国内可访问性改动（勿回退）

为让页面在国内网络下正常打开，源文件做了四处改动，**改代码时请保留**：

| 位置 | 内容 | 原因 |
|---|---|---|
| `loadLeafletAssets` | `css.href='vendor/leaflet/leaflet.css'`、`s.src='vendor/leaflet/leaflet.js'` | 原为 `unpkg.com`，境外 CDN 时快时慢 |
| `renderLeafletMap` | 瓦片源 `webrd0{s}.is.autonavi.com/appmaptile?...`（高德） | 原为 `tile.openstreetmap.org`，国内基本加载不出来 |
| `renderLeafletMap` | 渲染前重置 `#map-container`（清 `_leaflet_id`、换新节点） | 腾讯地图 GlJS 已初始化容器时，Leaflet 会抛 `Map container is already initialized`，导致只剩 SVG 静态图 |
| `DOMContentLoaded` | GlJS `onload` 里 1.5s 检测 + 硬兜底 2s | 腾讯地图 key 无效时不触发回调，需超时回退到高德瓦片 |

路径一律用**相对路径** `vendor/...`，同时兼容 GitHub Pages（根目录）与自建服务器（子路径 `/zzz/`）。
