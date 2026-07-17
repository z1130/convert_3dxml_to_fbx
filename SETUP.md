# 3DXML → FBX 转换工具 — 使用手册

把 CATIA V5 导出的 **.3dxml** 文件拖进网页，一键转成 **.fbx**（Three.js 和 Unity 都能直接用，尺寸已调好）。

**你不需要安装任何东西**：不用装 Python、不用装 Blender、不用联网。Windows 10 或更新版本即可。

---

## 一、快速上手（3 步）

```
① 解压压缩包到任意目录（建议纯英文路径，如 D:\converter\）
② 双击 converter.exe —— 浏览器会自动打开转换页面
③ 把 .3dxml 文件（或整个文件夹）拖进页面 → 自动转换 → 点「下载 FBX」
```

就这三步。用完直接**关掉黑色控制台窗口**即可（服务停止，临时文件自动删除，电脑不留痕）。

> 💡 首次运行如果 Windows 防火墙弹窗，点「允许」。浏览器没自动打开时，看控制台窗口里的地址（形如 `http://127.0.0.1:端口号/`），手动复制到浏览器打开。

---

## 二、页面怎么用

| 界面元素 | 作用 |
|---|---|
| 拖拽区 / 「选择文件」/「选择文件夹」 | 添加要转换的 .3dxml（文件夹会扫描全部子目录，可一次多个） |
| 任务列表 | 每个文件一张卡片，实时显示：排队中 / 转换中 / 成功 / 失败 |
| 右上角「?」帮助按钮 | 点击展开使用说明弹窗 |
| 「下载 FBX」 | 转换成功后，下载单个结果 |
| 「3D 预览」 | 页面内直接查看模型（鼠标左键旋转、滚轮缩放、右键平移；可切线框、重置视角） |
| 「全部下载（ZIP）」 | 把所有成功的结果打包成一个 zip（保持原文件夹目录结构） |
| 「清空列表」 | 清空任务列表（需确认） |
| 「重试」 | 转换失败后重新转换 |
| 底部状态栏 | 绿点 = 服务正常运行中 |

---

## 三、命令行用法（可选，适合批处理/脚本）

`converter.exe` 同时也是命令行工具，在 cmd / PowerShell 里：

```bash
# 单文件转换（输出同名 input.fbx）
converter.exe input.3dxml

# 指定输出文件名
converter.exe input.3dxml output.fbx

# 批量转换整个文件夹（-r 递归子目录）
converter.exe 某文件夹/ -r -o 输出文件夹/

# 批量时某个失败也继续
converter.exe 某文件夹/ -o 输出文件夹/ --continue-on-error
```

---

## 四、多人共用（局域网）

只需在**一台**电脑（Windows 10+）上运行，其他人用浏览器访问：

```bash
converter.exe serve --host 0.0.0.0 --port 8000
```

然后团队任何电脑（包括 Win7、Mac）浏览器打开 `http://<这台电脑的IP>:8000/` 即可使用。多人同时转换会自动排队。

---

## 五、部署到服务器（IT / 管理员）

### 方案 A：Windows 服务器（最简单）

分发包解压到服务器，执行：

```bash
converter.exe serve --host 0.0.0.0 --port 8000 --no-browser
```

- 防火墙放行 8000 端口；
- 常驻运行：「任务计划程序」设开机启动 + 失败重启，或用 NSSM 注册成 Windows 服务。

### 方案 B：Linux 服务器

```bash
git clone https://github.com/z1130/convert_3dxml_to_fbx.git && cd convert_3dxml_to_fbx
sudo apt install python3.13 python3-pip
python3.13 -m pip install bpy flask --target=./vendor
sudo apt install libgl1 libxi6 libxxf86vm1 libxfixes3 libxrender1   # bpy 无头运行依赖
python3.13 app.py serve --host 0.0.0.0 --port 8000 --no-browser
```

systemd 常驻（`/etc/systemd/system/converter.service`）：

```ini
[Unit]
Description=3DXML to FBX Converter
After=network.target

[Service]
WorkingDirectory=/opt/convert_3dxml_to_fbx
ExecStart=/usr/bin/python3.13 app.py serve --host 0.0.0.0 --port 8000 --no-browser
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

### 部署注意点

1. **文件安全**：上传的 .3dxml 和产物 .fbx 都在服务器临时目录，**服务停止即自动删除**，服务器不保留用户文件；
2. **并发**：转换内部串行排队（bpy 限制），多人同时使用无需配置；
3. **HTTPS/域名**：需要时前置 nginx（`proxy_pass http://127.0.0.1:8000`，大文件上传设 `client_max_body_size 2g`）；
4. **公网暴露必须加鉴权**：服务本身无登录，请在 nginx 层加 basic auth 或 IP 白名单。

---

## 六、常见问题

**Q：双击 exe 没反应 / 浏览器没打开？**
A：看黑色控制台窗口里的地址（`http://127.0.0.1:.../`），手动复制到浏览器。防火墙弹窗选「允许」。

**Q：Win7 能用吗？**
A：不能直接运行（需要 Windows 10+）。Win7 电脑可以用「四、多人共用」方式，浏览器访问别的机器。

**Q：转换失败提示「File is not a zip file」或解析错误？**
A：这个文件损坏了，或者它是二进制格式的 3DXML（CATIA 另一种导出配置）。本工具只支持 XML 型 3DXML。

**Q：转出来的 FBX 在 Unity 里尺寸不对？**
A：不会的。工具已自动做 Unity 兼容处理，Three.js 和 Unity 里视觉尺寸一致。

**Q：上传的文件会泄露吗？**
A：不会。文件只存在本机（或服务端）临时目录，服务关闭即删除，不联网、不上传到任何外部服务器。

**Q：页面里转换大文件卡住不动？**
A：大文件转换需要几十秒属正常（进度条是动画而非真实百分比）。耐心等待即可，转换成功会有提示。

---

## 七、附录：从源码构建分发包（仅打包者）

终端用户请忽略本节。构建机需要：Windows 10+、Python 3.13、MSVC（VS 2022 / Build Tools）。

```bash
# 1. 装依赖到 ./vendor（bpy 约 350MB）
python313 -m pip install bpy flask nuitka --target=./vendor

# 2. 一键构建（首次约 10–30 分钟，产出 dist/）
python tools/build.py
```

产出 `dist/`（约 1GB，自包含、无源码）压缩即可分发。技术细节见仓库 `README.md`。
