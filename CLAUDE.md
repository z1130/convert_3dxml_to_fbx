# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目性质

**3DXML → FBX 转换工具**（非传统软件项目，无构建系统/测试框架/依赖管理）。核心是两个 Blender 脚本 + 一个 HTML 验证页，把 CATIA V5 导出的 3DXML 转为 Three.js FBXLoader 可用的 FBX。`README.md` 含完整用法。

## 必须用 Blender 运行（关键约束）

脚本依赖 `bpy`（Blender 内置模块），**普通 `python` 无法运行**。所有脚本都以 headless 方式调用：

```bash
"E:\Blender\blender.exe" --background --factory-startup --python <script>.py -- <args...>
```

- `--factory-startup` 跳过用户配置，保证干净环境。
- `--` 之后的参数才传给脚本（脚本内 `sys.argv[argv.index('--')+1:]` 解析）。
- 本机 Blender 5.0 在 `E:\Blender\blender.exe`（内置 Python 3.11）。

常用命令：
```bash
# 转换
"E:\Blender\blender.exe" --background --factory-startup --python convert_3dxml_to_fbx.py -- lzh.3dxml out.fbx
# 回读验证
"E:\Blender\blender.exe" --background --factory-startup --python __test__/verify_fbx.py -- out.fbx
# FBXLoader 浏览器实测（需先起本地服务器避免 CORS）
python -m http.server 8000   # 然后浏览器开 http://127.0.0.1:8000/__test__/test_fbx_loader.html
```

## 转换脚本架构（convert_3dxml_to_fbx.py）

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

**④ 单位换算 + scale + 根基准点** — 3DXML 几何/平移是 mm：`parse_rep_file` 顶点与 `relmatrix_to_mat4` 平移都 ÷1000（`MM_TO_M`）。**对齐 CATIA/建模人员 FBX（Unity 友好）的导出配方（三要素缺一不可）**：① `clear_scene()` 末尾设 `scene.unit_settings.scale_length=0.01`（声明场景单位=cm）；② `export_fbx()` 用 `apply_unit_scale=True`；③ `global_scale=1.0`。三者配合抵消 Blender 的 m→cm 根 `scale=100` 补偿，得到根 `scale=(1,1,1)`、顶点与 `Lcl Translation` 均为米制——与建模人员手处理 FBX 逐节点 transform 完全同量级（实测同物体 max|T| 与各节点数值逐一吻合）。**关键：单独调 `apply_unit_scale`/`global_scale` 无法把根 scale 降到 1（实测 4 种组合最小只能 100），必须配 `scale_length=0.01`；且这些 kwarg 不碰几何顶点（4 种组合下顶点 SIZE 恒定）**。漏掉÷1000 会 position×1000；漏掉 `scale_length=0.01` 会根 scale=100 且 translation 同比×100。Unity 单位：FBX 头 `UnitScaleFactor` 由 `diagnose_fbx_units.py --patch` 写 100（Blender 硬编码 1.0，Unity 按 USF/100 缩放视觉尺寸），patch 只改 2 个 double、不动几何/transform。构建后 `world_bbox()`（前置 `bpy.context.view_layer.update()` 刷新 matrix_world）算包围盒中心，上提到根节点（`root_obj.location=C`，顶层子节点 `matrix_basis.translation-=C`），使 `root.position`=模型几何中心、世界坐标不变。调单位配方后用 `__test__/verify_export_scale.py`（Blender 内跑）回归：4 配置 × patch USF=100，回读根 scale + 顶点 SIZE 对照标杆。

装配树展开用 `obj.matrix_parent_inverse = Identity` + `obj.matrix_basis = relative_matrix`，保证 `matrix_basis` 就是 local→parent 的 RelativeMatrix。

## 几何三角化规则（expand_face）

`strips` 段内第 i 个三角形按奇偶位翻转缠绕（`if i%2==1: swap a,b`）保证法线一致；`fans` 首点为中心 `(c, v[i], v[i+1])`。改这里会批量翻转法线。

## 验证页（test_fbx_loader.html）

用 importmap 从 unpkg CDN 加载 three@0.160 + FBXLoader，渲染 `out.fbx` 并打印 mesh/三角面/包围盒。改 axis/矩阵后用此页确认渲染效果。需本地服务器（非 file://）。

## 数据文件说明

- `lzh.3dxml` — 示例输入（zip）。解压后内部含 `test.3dxml`(产品结构)、`Manifest.xml`(入口)、`*.3DRep`(几何：`NonAscii_6/9` 为空 `<Root/>`、`229009.3DRep` 是主大件)、`CATMaterialRef.3dxml` + `material_*_Rendering.3DRep`(材质库 OSM，**缺到零件的绑定**，故用面内联 RGBA 降级)。脚本运行时自动解压到系统临时目录，无需手动解压。
- `out.fbx` — 转换输出（可重新生成）。

## 仅支持 XML 型 .3DRep

二进制 `.3DRep`（CGR/CGM）为达索私有，无开源解。所有几何解析基于 `XMLRepresentation`/`PolygonalRepType`。
