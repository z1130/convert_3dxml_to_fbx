# 3DXML → FBX 转换工具 — 安装与使用

## 这个工具做什么

把 CATIA V5 导出的 **3DXML** 文件转成 **FBX**。同一个 FBX 同时兼容：

- **Three.js**（Web 端，FBXLoader 直接加载）
- **Unity**（视觉尺寸与 Three.js 一致，已自动处理 UnitScaleFactor）

---

## 你需要装什么

**只需要装 Blender（4.0 ~ 5.0）。** Python 不是必需的 —— 装了命令更短，不装也能用（走 Blender 自带的 Python）。

### 第一步：安装 Blender

1. 下载：<https://www.blender.org/download/>
2. 版本：4.0 / 4.1 / 4.2 / 5.0 任一均可
3. **强烈建议用默认路径安装**（Windows 下即 `C:\Program Files\Blender Foundation\Blender X.X\`）。默认路径装好后**无需任何配置**，工具会自动找到 Blender。

### 第二步：（仅当未用默认路径）告诉工具 Blender 在哪

如果 Blender 装在非默认路径，三选一即可：

- **改 `config.json`（推荐）**：用记事本打开本目录下的 `config.json`，把 `blender_path` 填成你的 `blender.exe` 完整路径，例如：
  ```json
  {
    "blender_path": "D:/MyApps/Blender/blender.exe"
  }
  ```
- **设环境变量**：新增系统环境变量 `BLENDER`，值设为 `blender.exe` 完整路径。
- **临时指定**：每次转换命令里加 `--blender "你的路径/blender.exe"`。

---

## 怎么用

打开命令行：在工具文件夹的地址栏输入 `cmd` 回车，然后按下面操作。

### 情况 A：装了 Python（命令更短）

```
python convert.py input.3dxml
```

### 情况 B：没装 Python（用 Blender 自带的 Python）

```
"C:/Program Files/Blender Foundation/Blender 5.0/blender.exe" --background --factory-startup --python convert.py -- input.3dxml
```

> 路径里的版本号 `5.0` 按你实际装的版本改。`--` 后面跟的是参数。

### 常用参数

| 用途 | 命令 |
|---|---|
| 单文件转换（默认输出同名 `input.fbx`） | `python convert.py input.3dxml` |
| 指定输出文件名 | `python convert.py input.3dxml output.fbx` |
| 批量转换整个目录 | `python convert.py 某目录/ -o 输出目录/` |
| 递归扫描子目录 | `python convert.py 某目录/ -r -o 输出目录/` |
| 批量时单个失败也继续 | 末尾加 `--continue-on-error` |
| 转换后自检（Blender 回读验证） | 末尾加 `--verify` |

> 没装 Python 时，把上表里的 `python convert.py` 替换成情况 B 那段 `"...blender.exe" --background --factory-startup --python convert.py --`，后面参数照搬。

---

## 常见问题

**Q: 报错「找不到 Blender」。**
A: 你没按默认路径装 Blender，也没配 `config.json`。回到上面"第二步"配置一次。

**Q: 报错「输入文件不是 .3dxml」。**
A: 文件后缀不对。本工具只接受 `.3dxml` 后缀的文件。

**Q: 转换过程中报了一堆错，怎么定位？**
A: 日志里 `[error]` 开头的就是原因。常见是：3DXML 文件损坏；或该文件是二进制 CGR/CGM 格式（部分 CATIA 配置导出二进制，**本工具不支持**，只支持 XML 型）。

**Q: 转出来的 FBX 在 Unity 里太小或太大。**
A: 工具默认已把 `UnitScaleFactor` 设为 100（Unity 友好）。确认你没加 `--no-patch` 参数（加了等于只给 Three.js 用，不兼容 Unity）。

**Q: 想看完整技术文档。**
A: 读本目录下的 `README.md`。
