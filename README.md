# 3DXML → FBX 转换工具

将 CATIA V5 导出的 **3DXML**（zip 压缩包）转换为 **FBX**，产物同时兼容：

- **Web 端 Three.js `THREE.FBXLoader`**
- **Unity FBX 导入器**

保留装配层级、多色材质、零错加载。默认输出已完成 USF=100 单位修补，无需为 Unity 单独导出第二份。

---

## 一、环境要求

| 项 | 要求 |
|---|---|
| Python | **3.13**（bpy 官方 wheel 仅发布 cp313，其他版本无法加载） |
| bpy 包 | 安装到本项目 `./pip` 目录（见 `SETUP.md`） |

> 核心转换脚本依赖 `bpy`（Blender Foundation 官方 PyPI 包），**无需安装 Blender**。`convert.py` 顶部把 `./pip` 注入 `sys.path` 后在进程内直接调用，无需手动写 Blender 命令。

---

## 二、配置

### 首次安装 bpy

`bpy` 是 Blender Foundation 官方 PyPI 包，**必须 Python 3.13**，且需装到项目根目录 `./pip` 下：

```bash
# Windows
"C:/Users/<用户名>/AppData/Local/Programs/Python/Python313/python.exe" -m pip install bpy --target=./pip

# Linux
python3.13 -m pip install bpy --target=./pip
```

- 把 `<用户名>` 换成你的实际用户名。
- 下载量约 350MB，请耐心等待。
- 装好后工具目录下会出现 `pip/` 文件夹。
- Windows 与 Linux 不能混用 `./pip`，各系统需各自重装。

### 指定 Python 3.13 路径（可选）

若 `python` 默认不是 3.13，或 Python 3.13 装在非默认路径，编辑 `config.json` 指定解释器路径：

```json
{
  "python_path": "C:/Users/<用户名>/AppData/Local/Programs/Python/Python313/python.exe"
}
```

若未配置，`convert.py` 会依次尝试 `PYTHON313` 环境变量、`PATH` 中的 `python3.13`，以及常见安装路径，找到后自动用 `os.execv` 切换到 3.13 运行。

---

## 三、快速使用

### 转换

```bash
# 单文件：默认输出与输入同名
python convert.py input.3dxml

# 单文件：指定输出文件名
python convert.py input.3dxml output.fbx

# 批量：转换目录下所有 .3dxml，输出到同目录
python convert.py resources/

# 批量：转换目录下所有 .3dxml，输出到指定目录
python convert.py resources/ -o output_fbx

# 批量：递归扫描子目录
python convert.py resources -r -o output_fbx

# 转换 + Blender 回读验证
python convert.py input.3dxml --verify

# 跳过 Unity 兼容 patch（极少需要）
python convert.py input.3dxml --no-patch
```

执行后会自动完成：

1. 进程内调用 `bpy` 导出中间 FBX。
2. `diagnose_fbx_units.patch` 将 `UnitScaleFactor` 设为 `100.0`，使 Unity 视觉尺寸与 Three.js 一致。
3. 若带 `--verify`，再用 bpy 回读校验结构/几何/材质。
4. 输出目录不存在时自动创建（单文件 `out/output.fbx` 或批量 `-o output_fbx` 均适用）。

### 参数说明

| 参数 | 说明 | 默认值 | 示例 |
|---|---|---|---|
| `input` | 输入 `.3dxml` 文件路径或目录 | 必填 | `python convert.py input.3dxml` |
| `output` | 单文件模式下输出 `.fbx` 路径 | 与输入同名 | `python convert.py input.3dxml output.fbx` |
| `-o, --output-dir` | 批量模式下指定输出目录 | 与输入同目录 | `python convert.py resources/ -o output_fbx` |
| `-r, --recursive` | 递归扫描子目录中的 `.3dxml` | 仅当前目录 | `python convert.py resources -r -o output_fbx` |
| `--no-patch` | 跳过 USF=100 patch | 默认启用 patch | `python convert.py input.3dxml --no-patch` |
| `--verify` | 转换后回读验证 | 默认不验证 | `python convert.py input.3dxml --verify` |
| `--continue-on-error` | 批量模式下单个失败后继续 | 默认遇到失败即停止 | `python convert.py resources/ -o output_fbx --continue-on-error` |

---

## 四、输出说明

- **格式**：binary FBX 7.4（FBXLoader 友好）
- **坐标系**：Y-up（对应 CAD Exchanger 的 "Use OY as Up axis"）
- **单位**：3DXML 原始 mm → 米（÷1000），根节点 `scale≈1`、坐标为米级小值；根节点 `position` = 模型几何中心（包围盒中心上提），可直接用于定位
- **结构**：`Group`(装配根) → 子 `Group`(子装配) / `Mesh`(零件)，实例已展开
- **材质**：每个面的内联 RGBA 颜色 → Principled BSDF，按颜色分多材质槽
- **Unity 兼容**：FBX 头 `UnitScaleFactor = 100.0`，Unity 按 `USF/100` 缩放后视觉尺寸与 Three.js 一致

---

## 五、验证产物

### 1. bpy 回读（结构/几何/材质核对）

```bash
python convert.py input.3dxml --verify
```

打印装配树、每个 Mesh 的顶点/材质数、材质颜色样本、世界包围盒。

### 2. THREE.FBXLoader 浏览器实测（关键）

```bash
# 项目根目录启动本地服务器（避免 file:// 的 CORS）
python -m http.server 8000
```

浏览器打开：

```
http://127.0.0.1:8000/__test__/test_fbx_loader.html?model=../input.fbx
```

页面用 FBXLoader 加载 `input.fbx` 并渲染，左上角输出：mesh 数、三角面数、包围盒。控制台应无 FBX 相关报错。

> `?model=../xxx.fbx` 可改为任意项目根目录下的 FBX 文件，**必须提供该参数**，否则页面会提示缺少模型路径。

---

## 六、技术实现要点

| 维度 | 实现 |
|---|---|
| 几何解析 | `.3DRep` 的 `XMLRepresentation`/`PolygonalRepType`：`VertexBuffer.Positions`/`Normals` + `Face` 的 `triangles`/`strips`/`fans`（全部三角化，strips 按奇偶位翻转缠绕） |
| 装配树 | `Reference3D`/`Instance3D` 递归**展开实例**（同一零件被多次实例化时，每个实例生成独立节点 + 独立 mesh，因 FBXLoader 不支持实例化引用） |
| 变换矩阵 | `RelativeMatrix` **列优先**（OpenGL/GLC_lib 约定）：前 9 个填旋转（按列），后 3 个为平移；语义为 local→parent，直接作 `matrix_local` |
| Up 轴 | **Y-up**（Blender 内用原始坐标，导出 `axis_up='Y'`） |
| 单位 | mm → 米；Blender 场景 `scale_length=0.01` + `apply_unit_scale=True` + `global_scale=1.0`，使根 `scale≈1`、顶点/位移为米级 |
| Unity 兼容 | 导出后 patch `UnitScaleFactor`/`OriginalUnitScaleFactor` 为 `100.0`；Unity 按 `USF/100` 缩放，视觉尺寸与 Three.js 一致 |
| 节点精简 | 跳过无几何的空叶子节点（如空 `.3DRep` 引发的冗余 Empty） |
| 材质 | 因 3DXML 缺「材质库→零件」绑定关系，用每个 `Face` 的内联 RGBA 纯色降级 |
| LOD | 每个 `PolygonalRepType` 优先取直接子 `<Faces>`（最高精度），缺失时取 `accuracy` 最小的 `PolygonalLOD` |

---

## 七、手动调用（高级用户 / 故障排查）

若不想用 wrapper，可手动执行两步（需用 Python 3.13，脚本会自动加载 `./pip/bpy`）：

```bash
# 1. bpy 导出
python convert_3dxml_to_fbx.py input.3dxml input.fbx

# 2. patch USF=100（Unity 兼容必需）
python diagnose_fbx_units.py --patch input.fbx input.fbx
```

---

## 八、调整朝向（不同模型可能不同）

若默认朝向不符合预期，编辑 `convert_3dxml_to_fbx.py` 的 `export_fbx()` 函数中的 axis 参数：

```python
axis_forward='-Z',   # 可选: '-Z' / 'Y' / '-Y' / 'X' ...
axis_up='Y',         # 可选: 'Y' / 'Z'   ← CAD/3DXML 常见为 Y-up 或 Z-up
```

| 现象 | 调整 |
|---|---|
| 模型竖直立起来 | 改 `axis_up`（Y↔Z） |
| 模型侧躺/翻转 | 改 `axis_forward` |
| 左右镜像 | 调 `axis_forward` 正负 |

> 矩阵旋转约定（行/列优先）若需切换，编辑 `relmatrix_to_mat4()`：列优先用 `(v0,v3,v6...)`，行优先用 `(v0,v1,v2...)`。

---

## 九、文件清单

| 文件 | 作用 |
|---|---|
| **根目录（核心）** | |
| `convert.py` | **一键转换 wrapper**（自动 export + patch + 可选 verify） |
| `config.json` | Python 3.13 路径配置（`python_path`，随仓库提交，用户拿到后修改本地路径） |
| `convert_3dxml_to_fbx.py` | **主转换脚本**（被 wrapper 调用） |
| `diagnose_fbx_units.py` | FBX 单位元数据读写/修补（`--patch` 写 `UnitScaleFactor=100`，Unity 兼容） |
| `build.py` | 一键构建分发包到 `dist/`（发给用户） |
| `SETUP.md` | 面向零环境用户的安装使用文档 |
| **`__test__/`（验证 / 对比）** | |
| `verify_fbx.py` | Blender 回读验证脚本 |
| `verify_export_scale.py` | 导出单位配置回归（Blender 内跑，需传入 `.3dxml` 和参考 `.fbx`） |
| `compare_fbx.py` | 裸 FBX 二进制对比（顶点量级 + Model transform） |
| `compare_in_blender.py` | Blender 导入双 FBX 对比 |
| `test_fbx_loader.html` | THREE.FBXLoader 浏览器测试页 |
| **数据** | |
| `input.3dxml` | 示例输入 |
| `input.fbx` | 转换输出（可随时重新生成，默认与输入同名） |

---

## 十、分发给他人使用

### 1. 构建分发包

```bash
python build.py
```

生成 `dist/`，只含用户运行所需文件（排除示例数据与开发产物），并自动写入空路径版 `config.json`。**直接把整个文件夹发给用户即可，无需打包成 zip。**

分发包内容：

| 文件 | 作用 |
|---|---|
| `convert.py` / `convert_3dxml_to_fbx.py` / `diagnose_fbx_units.py` | 核心转换 |
| `__test__/verify_fbx.py` | `--verify` 依赖 |
| `config.json` | `python_path` 留空，走自动探测 |
| `README.md` / `SETUP.md` | 完整文档 / 用户向安装文档 |

### 2. 用户需要装什么

**装 Python 3.13 + bpy 包（装到 `./pip`），默认路径安装即可免配置。** 不需要安装 Blender。详见分发包内的 `SETUP.md`。

> `./pip`（bpy 依赖，350MB+）不打包进 dist，用户拿到分发包后需自行执行：`"<Python313>/python.exe" -m pip install bpy --target=./pip`

脚本更新后再次执行 `python build.py` 即可刷新分发包（会先清空旧目录）。

---

## 十一、已知限制

1. **仅支持 XML 型 `.3DRep`**：二进制型 `.3DRep`（CATIA CGR/CGM 内核变体）为达索私有格式，无开源解析方案。
2. **材质库无法精确绑定**：`material_47/52/59` 等 OSM 物理材质定义存在，但 3DXML 中缺到具体零件的绑定节点 → 用面内联纯色降级（颜色准确，丢失反射率/折射率等物理参数）。
3. **单位**：原始为 mm，脚本自动换算为**米**（÷1000），导出 `scale≈1`、坐标为米级小值。根节点 `position` = 模型几何中心（包围盒中心上提），可直接用于定位。`scale` 数值可能是 `0.9999999999999999`（Blender 浮点精度，等同 1），如需严格 `1` 可加载后 `fbx.scale.set(1,1,1)` 归一化。
4. **空零件**：源 `.3DRep` 为空（`<Root/>`）的零件（如某些标准件）不会生成几何节点。
