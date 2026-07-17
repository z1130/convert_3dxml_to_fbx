/**
 * preview.js - FBX 3D 预览抽屉的渲染模块（本地化 three@0.169，离线可用）
 *
 * 导出 createPreview(container) → { load(url, name), resetView(), setWireframe(bool), dispose() }
 * 只依赖传入的容器元素，与页面其余 DOM 解耦。
 */

import * as THREE from 'three';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';

export function createPreview(container, { onLoaded, onError } = {}) {
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x010409);

  const camera = new THREE.PerspectiveCamera(50, 1, 0.01, 200000);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  container.appendChild(renderer.domElement);

  const controls = new OrbitControls(camera, renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x333a45, 1.1));
  const dir = new THREE.DirectionalLight(0xffffff, 1.8);
  dir.position.set(1, 2, 3);
  scene.add(dir);

  let current = null;   // 当前模型 Object3D
  let grid = null;
  let home = null;      // 初始相机位姿（重置视角用）
  let disposed = false;

  function resize() {
    const w = container.clientWidth || 1;
    const h = container.clientHeight || 1;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h);
  }
  const ro = new ResizeObserver(resize);
  ro.observe(container);
  resize();

  function animate() {
    if (disposed) return;
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();

  function clearModel() {
    if (current) {
      scene.remove(current);
      current.traverse((n) => {
        if (n.isMesh) {
          n.geometry && n.geometry.dispose();
          const mats = Array.isArray(n.material) ? n.material : [n.material];
          mats.forEach((m) => m && m.dispose && m.dispose());
        }
      });
      current = null;
    }
    if (grid) {
      scene.remove(grid);
      grid = null;
    }
  }

  function frameModel(obj) {
    const box = new THREE.Box3().setFromObject(obj);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const maxDim = Math.max(size.x, size.y, size.z) || 1;

    grid = new THREE.GridHelper(maxDim * 2, 20, 0x2d333b, 0x21262d);
    grid.position.set(center.x, box.min.y, center.z);
    scene.add(grid);

    camera.position.set(
      center.x + maxDim * 1.2,
      center.y + maxDim * 0.9,
      center.z + maxDim * 1.2,
    );
    controls.target.copy(center);
    controls.update();
    home = { pos: camera.position.clone(), target: controls.target.clone() };

    // 统计信息（等宽字体展示在信息条）
    let verts = 0, tris = 0;
    obj.traverse((n) => {
      if (n.isMesh) {
        const pos = n.geometry && n.geometry.attributes.position;
        if (pos) {
          verts += pos.count;
          tris += n.geometry.index ? n.geometry.index.count / 3 : pos.count / 3;
        }
      }
    });
    return { verts, tris: Math.round(tris), size };
  }

  function load(url, name) {
    clearModel();
    new FBXLoader().load(
      url,
      (obj) => {
        current = obj;
        scene.add(obj);
        const info = frameModel(obj);
        onLoaded && onLoaded({ name, ...info });
      },
      undefined,
      (err) => {
        console.error(err);
        onError && onError(err);
      },
    );
  }

  return {
    load,
    resetView() {
      if (!home) return;
      camera.position.copy(home.pos);
      controls.target.copy(home.target);
      controls.update();
    },
    setWireframe(flag) {
      if (!current) return;
      current.traverse((n) => {
        if (n.isMesh) {
          const mats = Array.isArray(n.material) ? n.material : [n.material];
          mats.forEach((m) => { if (m) m.wireframe = flag; });
        }
      });
    },
    dispose() {
      disposed = true;
      ro.disconnect();
      clearModel();
      renderer.dispose();
      renderer.domElement.remove();
    },
  };
}
