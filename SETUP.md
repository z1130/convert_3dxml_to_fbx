# 3DXML → FBX 转换工具 — 安装与使用

## 这个工具做什么

把 CATIA V5 导出的 **3DXML** 文件转成 **FBX**。同一个 FBX 同时兼容：

- **Three.js**（Web 端，FBXLoader 直接加载）
- **Unity**（视觉尺寸与 Three.js 一致，已自动处理 UnitScaleFactor）

---

## 你需要装什么

**只需要 Python 3.13 + bpy 包。** 不需要安装 Blender。

### 第一步：安装 Python 3.13

bpy 官方 wheel 仅支持 Python 3.13（其他版本无法加载，会报 DLL load failed）。

1. 下载：<https://www.python.org/downloads/release/python-3130/>
2. 安装时勾选 “Add python.exe to PATH”。
3. **强烈建议用默认路径安装**（Windows 下即 `C:\Users\<用户名>\AppData\Local\Programs\Python\Python313\`）。默认路径装好后**无需任何配置**，工具会自动找到。

### 第二步：安装 bpy（一次性）

打开命令行（在工具文件夹地址栏输入 `cmd` 回车），执行：

```bash
"C:/Users/<用户名>/AppData/Local/Programs/Python/Python313/python.exe" -m pip install bpy --target=./pip
```

- 把 `<用户名>` 换成你的实际用户名。
- `--target=./pip` 把 bpy 装到工具目录下的 `pip/` 子目录，**不污染系统环境**。
- 下载量约 350MB，请耐心等待。
- 装好后工具目录下会出现 `pip/` 文件夹。

### 第三步：（仅当未用默认路径）告诉工具 Python 3.13 在哪

如果 Python 3.13 装在非默认路径，二选一即可：

- **改 `config.json`（推荐）**：用记事本打开本目录下的 `config.json`，把 `python_path` 填成你的 `python.exe` 完整路径，例如：
  ```json
  {
    "python_path": "D:/Python313/python.exe"
  }
  ```
- **设环境变量**：新增系统环境变量 `PYTHON313`，值设为 `python.exe` 完整路径。

### Linux 用户

```bash
# 1. 装 Python 3.13（Ubuntu/Debian 示例；其他发行版用对应包管理器）
sudo apt install python3.13 python3-pip

# 2. 装 bpy 到项目 ./pip（pip 会自动拉 manylinux wheel）
python3.13 -m pip install bpy --target=./pip

# 3. 转换（python3.13 通常已在 PATH，无需改 config.json）
python3.13 convert.py input.3dxml
```

> 若 `import bpy` 报缺失 `.so`（如 `libGL.so`、`libX11.so`），bpy 依赖系统图形库，执行：
> `sudo apt install libgl1 libxi6 libxxf86vm1 libxfixes3 libxrender1`

---

## 怎么用

打开命令行（在工具文件夹的地址栏输入 `cmd` 回车），然后执行：

```bash
python convert.py input.3dxml
```

> 即使 `python` 默认不是 3.13，工具也会自动找到 3.13 并切换，无需手动指定解释器。

### 常用参数

| 用途 | 命令 |
|---|---|
| 单文件转换（默认输出同名 `input.fbx`） | `python convert.py input.3dxml` |
| 指定输出文件名 | `python convert.py input.3dxml output.fbx` |
| 批量转换整个目录 | `python convert.py 某目录/ -o 输出目录/` |
| 递归扫描子目录 | `python convert.py 某目录/ -r -o 输出目录/` |
| 批量时单个失败也继续 | 末尾加 `--continue-on-error` |
| 转换后自检（回读验证） | 末尾加 `--verify` |

---

## 常见问题

**Q: 报错「找不到 Python 3.13」。**
A: 你没装 Python 3.13，或装在非默认路径且没配 `config.json`。回到上面“第一步 / 第三步”。

**Q: 报错「未找到 bpy 安装目录: .../pip」。**
A: 你没执行第二步安装 bpy。在工具目录下跑 `"<Python313>/python.exe" -m pip install bpy --target=./pip`。

**Q: 报错「加载 bpy 失败 ... DLL load failed」。**
A: 当前 Python 版本不对。bpy wheel 仅支持 Python 3.13，确认装的是 3.13。

**Q: 报错「输入文件不是 .3dxml」。**
A: 文件后缀不对。本工具只接受 `.3dxml` 后缀的文件。

**Q: 转换过程中报了一堆错，怎么定位？**
A: 日志里 `[error]` 开头的就是原因。常见是：3DXML 文件损坏；或该文件是二进制 CGR/CGM 格式（部分 CATIA 配置导出二进制，**本工具不支持**，只支持 XML 型）。

**Q: 转出来的 FBX 在 Unity 里太小或太大。**
A: 工具默认已把 `UnitScaleFactor` 设为 100（Unity 友好）。确认你没加 `--no-patch` 参数（加了等于只给 Three.js 用，不兼容 Unity）。

**Q: 想看完整技术文档。**
A: 读本目录下的 `README.md`。
