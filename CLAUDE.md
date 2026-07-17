# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

**3DXML → FBX 转换工具**（非传统软件项目，无构建系统/测试框架/依赖管理）。核心是：两个 Blender 脚本 + 一个 Python wrapper + 一个 HTML 验证页，把 CATIA V5 导出的 3DXML 转为同时兼容 **Three.js FBXLoader** 和 **Unity** 的 FBX。`README.md` 含完整用法。

用户日常入口是 `convert.py`：它自动串行**进程内**调用 `convert_3dxml_to_fbx.convert()`（导出）和 `diagnose_fbx_units.patch`（改写 FBX 头 `UnitScaleFactor=100`，Unity 兼容）。

## 基于 pip 版 bpy 运行（关键约束）

核心转换脚本依赖 `bpy`，但**不再通过 Blender 二进制运行**——改用 pip 安装的 `bpy` wheel（Blender Foundation 官方发布于 PyPI），安装在项目根目录 `./vendor` 下。`convert.py` 顶部把 `./vendor` 注入 `sys.path` 后 `import bpy`，并在**同一进程内**直接调用 `converter.convert_3dxml_to_fbx.convert()` / `converter.verify_fbx.verify()`，无任何子进程。

**Python 版本锁定**：bpy wheel 仅发布 cp313（当前 `bpy 5.1.2`），**必须 Python 3.13** 才能加载。`convert.py` 的 `ensure_python313()` 检测当前解释器版本，若非 3.13，按优先级（`config.json.python_path` → `PYTHON313` 环境变量 → PATH → 默认安装路径）找到 Python 3.13 解释器，用 `os.execv` **重启自身**。用户无论用哪个 Python 启动 `convert.py` 都会自动切到 3.13，无需手动指定。

安装 bpy（一次性）：
```bash
"<Python313>/python.exe" -m pip install bpy --target=./vendor
```
本机 Python 3.13 在 `C:\Users\Administrator\AppData\Local\Programs\Python\Python313\python.exe`。

常用命令：
```bash
# 单文件转换（默认输出与输入同名：input.3dxml → input.fbx）
python convert.py input.3dxml
# 指定输出
python convert.py input.3dxml output.fbx

# 批量转换目录下所有 .3dxml
python convert.py resources/
# 批量转换并输出到指定目录（目录不存在会自动创建）
python convert.py resources/ -o output_fbx
# 递归扫描子目录
python convert.py resources -r -o output_fbx
# 批量时单个失败继续
python convert.py resources/ -o output_fbx --continue-on-error

# 转换 + 回读验证
python convert.py input.3dxml --verify

# 手动分步（高级用户 / 故障排查）
python converter/convert_3dxml_to_fbx.py input.3dxml input.fbx
python converter/diagnose_fbx_units.py --patch input.fbx input.fbx

# FBXLoader 浏览器实测（需先起本地服务器避免 CORS）
python -m http.server 8000
# 然后浏览器开 http://127.0.0.1:8000/tests/test_fbx_loader.html?model=../input.fbx

# 构建分发包（生成 dist/ 发给用户）
python tools/build.py
```

**进程内调用约定**（改 `convert.py` / 转换脚本必读）：转换与验证都是**同进程函数调用**（`_convert_module.convert(...)` / `_verify_module.verify(...)`），不再是子进程。`convert_3dxml_to_fbx.convert()` 在开头重置所有 module-level globals（`TMPDIR/REFERENCES/INSTANCES/PARSE_CACHE/NODE_COUNT/MESH_COUNT`），保证批量模式下多次调用互不污染——`PARSE_CACHE` 若不重置，第二个文件会复用上一文件的缓存而读到错误的解压几何。`diagnose_fbx_units.patch` 仍为进程内 import 调用。**改回 Blender 子进程会破坏整个工作流，勿改。**

## 转换脚本架构（converter/convert_3dxml_to_fbx.py）

单文件、线性 5 阶段流水线，理解全局需读整个文件：

1. **解压 + 定位**：`zipfile` 解压 3DXML，读 `Manifest.xml` 的 `<Root>` 得主结构文件（通常 `test.3dxml`）。
2. **解析产品结构**（`parse_structure`）：从主 `.3dxml` 的 `<ProductStructure>` 构建 `references`（Reference3D id→{name, rep_file}）和 `instances`（Instance3D 列表）。**关键映射**：`.3DRep` 几何文件经 `InstanceRep` 桥接到 Reference3D——`ReferenceRep` 本身**没有** `<IsAggregatedBy>`，必须走 `InstanceRep.IsAggregatedBy`(→Reference3D) + `IsInstanceOf`(→ReferenceRep)。
3. **解析几何**（`parse_rep_file`→`parse_cached`）：每个 `.3DRep` 内所有 `PolygonalRepType` 合并为单个 mesh。`VertexBuffer.Positions`/`Normals` 是顶点池，`Face` 的 `triangles`/`strips`/`fans` 是索引（合并多 rep 时索引需加偏移量）。
4. **构建场景**（`expand`）：递归**展开实例树**。
5. **导出 FBX**（`export_fbx`）：版本兼容地构造 kwargs。

## 四个非显然的技术约定（改动前必读）

**① 矩阵列优先（OpenGL/GLC_lib 约定）** — `relmatrix_to_mat4()`：3DXML `RelativeMatrix` 12 个值，前 9 个旋转**按列填**，后 3 个平移。这是行优先会出错的根因。若要切换约定：列优先用 `(v0,v3,v6...)`，行优先用 `(v0,v1,v2...)`。

**② Y-up** — `export_fbx()` 的 `axis_up='Y'`：对应 CAD Exchanger 的 "Use OY as Up axis"。3DXML 原数据 Y 轴是主方向（坐标量级 ~6000），Y 是 Up。错配会让模型竖起/倾倒。

**③ 每个实例独立 mesh** — `build_object_mesh()` 每次新建 mesh data（只缓存 XML 解析结果）。**不能**让多个 object 共享同一 mesh，否则 Blender FBX 导出器报 material-index 警告、FBXLoader 丢材质。

**④ 单位换算 + scale + 根基准点 + 双兼容 patch** — 3DXML 几何/平移是 mm：`parse_rep_file` 顶点与 `relmatrix_to_mat4` 平移都 ÷1000（`MM_TO_M`）。**对齐 CATIA/建模人员 FBX（Unity 友好）的导出配方（三要素缺一不可）**：① `clear_scene()` 末尾设 `scene.unit_settings.scale_length=0.01`（声明场景单位=cm）；② `export_fbx()` 用 `apply_unit_scale=True`；③ `global_scale=1.0`。三者配合抵消 Blender 的 m→cm 根 `scale=100` 补偿，得到根 `scale=(1,1,1)`、顶点与 `Lcl Translation` 均为米制——与建模人员手处理 FBX 逐节点 transform 完全同量级（实测同物体 max|T| 与各节点数值逐一吻合）。**关键：单独调 `apply_unit_scale`/`global_scale` 无法把根 scale 降到 1（实测 4 种组合最小只能 100），必须配 `scale_length=0.01`；且这些 kwarg 不碰几何顶点（4 种组合下顶点 SIZE 恒定）**。漏掉÷1000 会 position×1000；漏掉 `scale_length=0.01` 会根 scale=100 且 translation 同比×100。

**Unity + Three.js 双兼容**：Three.js 直接按几何顶点坐标渲染，忽略 FBX 头 `UnitScaleFactor`；Unity 则按 `UnitScaleFactor/100` 缩放视觉尺寸。Blender 的 FBX 导出器硬编码 `UnitScaleFactor=1.0`，导致 Unity 中模型缩小 100 倍。`convert.py` 导出后自动调用 `diagnose_fbx_units.py --patch` 将 `UnitScaleFactor`/`OriginalUnitScaleFactor` 写为 100，使 Unity 视觉尺寸与 Three.js 一致。patch 只改 2 个 double、不动几何/transform，因此**一个 FBX 即可同时满足 Web 端 Three.js 和 Unity**。构建后 `world_bbox()`（前置 `bpy.context.view_layer.update()` 刷新 matrix_world）算包围盒中心，上提到根节点（`root_obj.location=C`，顶层子节点 `matrix_basis.translation-=C`），使 `root.position`=模型几何中心、世界坐标不变。调单位配方后用 `tests/verify_export_scale.py`（Python 3.13 直跑，传入 `.3dxml` 和参考 `.fbx`）回归：5 配置 × patch USF=100，回读根 scale + 顶点 SIZE 对照标杆。

装配树展开用 `obj.matrix_parent_inverse = Identity` + `obj.matrix_basis = relative_matrix`，保证 `matrix_basis` 就是 local→parent 的 RelativeMatrix。

## 几何三角化规则（expand_face）

`strips` 段内第 i 个三角形按奇偶位翻转缠绕（`if i%2==1: swap a,b`）保证法线一致；`fans` 首点为中心 `(c, v[i], v[i+1])`。改这里会批量翻转法线。

## 验证页（tests/test_fbx_loader.html）

用 importmap 从 unpkg CDN 加载 three@0.160 + FBXLoader，渲染 FBX 并打印 mesh/三角面/包围盒。必须通过 URL 参数 `?model=../xxx.fbx` 指定加载文件，不传参会提示缺少模型路径。改 axis/矩阵后用此页确认渲染效果。需本地服务器（非 file://）。

## 数据文件说明

- `resources/` — 示例输入 `.3dxml` 与转换输出（不随仓库提交）。3DXML 为 zip：内部含 `test.3dxml`(产品结构)、`Manifest.xml`(入口)、`*.3DRep`(几何)、材质库 OSM（**缺到零件的绑定**，故用面内联 RGBA 降级）。脚本运行时自动解压到系统临时目录，无需手动解压。
- `config.json` — Python 3.13 解释器路径配置（`python_path`，随仓库提交，用户拿到后修改本地路径）。`./vendor/` 是 bpy wheel 安装目录（350MB+，不随仓库提交）。

## 仅支持 XML 型 .3DRep

二进制 `.3DRep`（CGR/CGM）为达索私有，无开源解。所有几何解析基于 `XMLRepresentation`/`PolygonalRepType`。
