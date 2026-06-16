# 3DXML → FBX 转换工具

将 CATIA V5 导出的 **3DXML**（zip 压缩包）转换为 **FBX**，产物兼容 **Three.js `THREE.FBXLoader`**（保留装配层级、多色材质、零错加载）。

---

## 一、环境要求

| 项 | 要求 |
|---|---|
| Blender | 5.0（本机路径 `E:\Blender\blender.exe`） |
| Python 依赖 | **无**（脚本仅用 Blender 内置 `bpy` + Python 标准库 `xml.etree`/`zipfile`/`mathutils`） |

> 脚本必须在 Blender 内运行（普通 `python` 无法 `import bpy`）。

---

## 二、快速使用

脚本依赖 Blender 的 `bpy` 模块，**必须用 Blender 运行**（普通 `python` 不行）。`--` 之后的参数才传给脚本。

### 各 Shell 的正确写法（重要）

不同 shell 调用 `blender.exe` 的语法不同。**PowerShell 必须加 `&` 调用操作符**，否则报 `Unexpected token 'background' in expression or statement`：

| Shell | 命令 |
|---|---|
| **PowerShell** | `& "E:\Blender\blender.exe" --background --factory-startup --python convert_3dxml_to_fbx.py -- lzh.3dxml out.fbx` |
| **CMD** | `"E:\Blender\blender.exe" --background --factory-startup --python convert_3dxml_to_fbx.py -- lzh.3dxml out.fbx` |
| **Git Bash** | `"/e/Blender/blender.exe" --background --factory-startup --python convert_3dxml_to_fbx.py -- lzh.3dxml out.fbx` |

> - **PowerShell**：`&` 是调用操作符，让引号路径被当作命令执行；少了 `&`，PowerShell 会把路径当字符串，`--background` 变成悬空的非法 token。
> - **CMD**：直接写引号路径即可当命令。
> - **Git Bash**：用 Unix 风格路径 `/e/Blender/blender.exe`。

### 参数（`--` 之后）

| 位置 | 含义 | 默认值 |
|---|---|---|
| 1 | 输入 `.3dxml` 路径 | `lzh.3dxml` |
| 2 | 输出 `.fbx` 路径 | `out.fbx` |

运行时控制台会打印：解析的零件（顶点/三角面数）、场景节点数、网格数、根节点基准点坐标、导出结果。

---

## 三、输出说明

- **格式**：binary FBX 7.4（FBXLoader 友好）
- **坐标系**：Y-up（对应 CAD Exchanger 的 "Use OY as Up axis"）
- **单位**：mm → 米（÷1000），根节点 `scale≈1`、坐标为米级小值；根节点 `position` = 模型几何中心（包围盒中心上提），可直接用于定位
- **结构**：`Group`(装配根) → 子 `Group`(子装配) / `Mesh`(零件)，实例已展开
- **材质**：每个面的内联 RGBA 颜色 → Principled BSDF，按颜色分多材质槽

---

## 四、验证产物

### 1. Blender 回读（结构/几何/材质核对）

```bash
"E:\Blender\blender.exe" --background --factory-startup --python verify_fbx.py -- out.fbx
```

打印装配树、每个 Mesh 的顶点/材质数、材质颜色样本、世界包围盒。

### 2. THREE.FBXLoader 浏览器实测（关键）

```bash
# 项目根目录启动本地服务器（避免 file:// 的 CORS）
python -m http.server 8000
```

浏览器打开 `http://127.0.0.1:8000/test_fbx_loader.html`，页面用 FBXLoader 加载 `out.fbx` 并渲染，左上角输出：mesh 数、三角面数、包围盒。控制台应无 FBX 相关报错。

---

## 五、技术实现要点

| 维度 | 实现 |
|---|---|
| 几何解析 | `.3DRep` 的 `XMLRepresentation`/`PolygonalRepType`：`VertexBuffer.Positions`/`Normals` + `Face` 的 `triangles`/`strips`/`fans`（全部三角化，strips 按奇偶位翻转缠绕） |
| 装配树 | `Reference3D`/`Instance3D` 递归**展开实例**（同一零件被多次实例化时，每个实例生成独立节点 + 独立 mesh，因 FBXLoader 不支持实例化引用） |
| 变换矩阵 | `RelativeMatrix` **列优先**（OpenGL/GLC_lib 约定）：前 9 个填旋转（按列），后 3 个为平移；语义为 local→parent，直接作 `matrix_local` |
| Up 轴 | **Y-up**（Blender 内用原始坐标，导出 `axis_up='Y'`） |
| 节点精简 | 跳过无几何的空叶子节点（如空 `.3DRep` 引发的冗余 Empty） |
| 材质 | 因 3DXML 缺「材质库→零件」绑定关系，用每个 `Face` 的内联 RGBA 纯色降级 |
| LOD | 每个 `PolygonalRepType` 优先取直接子 `<Faces>`（最高精度），缺失时取 `accuracy` 最小的 `PolygonalLOD` |

---

## 六、调整朝向（不同模型可能不同）

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

## 七、文件清单

| 文件 | 作用 |
|---|---|
| `convert_3dxml_to_fbx.py` | **主转换脚本** |
| `verify_fbx.py` | Blender 回读验证脚本 |
| `test_fbx_loader.html` | THREE.FBXLoader 浏览器测试页 |
| `lzh.3dxml` | 示例输入 |
| `out.fbx` | 转换输出（可随时重新生成） |

---

## 八、已知限制

1. **仅支持 XML 型 `.3DRep`**：二进制型 `.3DRep`（CATIA CGR/CGM 内核变体）为达索私有格式，无开源解析方案。
2. **材质库无法精确绑定**：`material_47/52/59` 等 OSM 物理材质定义存在，但 3DXML 中缺到具体零件的绑定节点 → 用面内联纯色降级（颜色准确，丢失反射率/折射率等物理参数）。
3. **单位**：原始为 mm，脚本自动换算为**米**（÷1000），导出 `scale≈1`、坐标为米级小值。根节点 `position` = 模型几何中心（包围盒中心上提），可直接用于定位。`scale` 数值可能是 `0.9999999999999999`（Blender 浮点精度，等同 1），如需严格 `1` 可加载后 `fbx.scale.set(1,1,1)` 归一化。
4. **空零件**：源 `.3DRep` 为空（`<Root/>`）的零件（如某些标准件）不会生成几何节点。
