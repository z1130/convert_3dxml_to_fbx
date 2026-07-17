/**
 * app.js - 3DXML → FBX Converter 界面交互逻辑
 *
 * 任务流：选择/拖入文件 → 入队 → 逐个 POST /convert（与服务端串行锁一致）
 *         → 成功（下载/预览）或失败（错误+重试）。
 * 预览抽屉由 preview.js（ES module）驱动，动态 import 按需加载 three.js。
 */

const $ = (sel) => document.querySelector(sel);

const state = {
  tasks: [],        // {key, file, relpath, status, serverId, error, size}
  converting: false,
  preview: null,    // createPreview 实例（懒加载）
  previewTaskKey: null,
};
let taskSeq = 0;

/* ---------- 工具 ---------- */

function fmtSize(bytes) {
  if (bytes == null) return '';
  if (bytes >= 1 << 20) return (bytes / (1 << 20)).toFixed(1) + ' MB';
  if (bytes >= 1 << 10) return (bytes / (1 << 10)).toFixed(1) + ' KB';
  return bytes + ' B';
}

function toast(message, type = 'info') {
  const box = $('#toasts');
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  box.appendChild(el);
  setTimeout(() => el.classList.add('show'), 16);
  setTimeout(() => {
    el.classList.remove('show');
    setTimeout(() => el.remove(), 300);
  }, 3200);
}

/* ---------- 文件收集（文件/文件夹、拖拽） ---------- */

function acceptFile(file, relpath) {
  if (!file.name.toLowerCase().endsWith('.3dxml')) {
    toast(`仅支持 .3dxml 文件：${file.name}`, 'error');
    return;
  }
  state.tasks.push({
    key: ++taskSeq,
    file,
    relpath: relpath || file.name,
    status: 'queued',
    serverId: null,
    error: null,
    size: null,
  });
}

/** 递归遍历拖入的目录项（webkitGetAsEntry），收集全部 .3dxml */
async function walkEntry(entry, prefix = '') {
  if (entry.isFile) {
    const file = await new Promise((res, rej) => entry.file(res, rej));
    acceptFile(file, prefix + file.name);
    return;
  }
  if (entry.isDirectory) {
    const reader = entry.createReader();
    // readEntries 分批返回，必须循环读到空
    for (;;) {
      const batch = await new Promise((res, rej) => reader.readEntries(res, rej));
      if (!batch.length) break;
      for (const child of batch) {
        await walkEntry(child, `${prefix}${entry.name}/`);
      }
    }
  }
}

async function handleDrop(e) {
  e.preventDefault();
  $('#dropzone').classList.remove('dragover');
  const items = e.dataTransfer.items;
  if (items && items.length && items[0].webkitGetAsEntry) {
    for (const item of items) {
      const entry = item.webkitGetAsEntry();
      if (entry) await walkEntry(entry);
    }
  } else {
    for (const file of e.dataTransfer.files) acceptFile(file);
  }
  pump();
}

function handlePick(files, withRelpath) {
  for (const file of files) {
    acceptFile(file, withRelpath ? (file.webkitRelativePath || file.name) : file.name);
  }
  pump();
}

/* ---------- 转换队列（逐个串行） ---------- */

async function pump() {
  if (state.converting) return;
  const task = state.tasks.find((t) => t.status === 'queued' || t.status === 'retry');
  if (!task) { render(); return; }

  state.converting = true;
  task.status = 'converting';
  render();

  const form = new FormData();
  form.append('file', task.file, task.file.name);
  form.append('relpath', task.relpath);

  try {
    const resp = await fetch('/convert', { method: 'POST', body: form });
    const data = await resp.json();
    if (resp.ok && data.ok) {
      task.status = 'done';
      task.serverId = data.id;
      task.size = data.size;
      toast(`转换成功：${task.file.name}`, 'success');
    } else {
      task.status = 'error';
      task.error = data.error || `HTTP ${resp.status}`;
    }
  } catch (err) {
    task.status = 'error';
    task.error = '网络错误：' + err.message;
  }

  state.converting = false;
  render();
  pump();
}

/* ---------- 渲染 ---------- */

const STATUS_META = {
  queued:     { text: '排队中', cls: 'queued' },
  converting: { text: '转换中', cls: 'converting' },
  done:       { text: '成功',   cls: 'done' },
  error:      { text: '失败',   cls: 'error' },
};

// 设计稿 SVG 图标（颜色已按状态烘焙，直接 <img> 引用）
const IC = {
  fileQueued: '/assets/icons/file.svg',
  fileConverting: '/assets/icons/file3.svg',
  fileDone: '/assets/icons/file1.svg',
  fileError: '/assets/icons/file0.svg',
  queued: '/assets/icons/clock.svg',
  converting: '/assets/icons/loader.svg',
  done: '/assets/icons/checkcircle.svg',
  error: '/assets/icons/xcircle.svg',
  download: '/assets/icons/download.svg',
  box: '/assets/icons/box.svg',
  refresh: '/assets/icons/refreshcw.svg',
  x: '/assets/icons/x.svg',
};

function taskCard(t) {
  const meta = STATUS_META[t.status];
  const isFolder = t.relpath !== t.file.name;
  const multi = t.status === 'converting' || t.status === 'error';
  const el = document.createElement('div');
  el.className = `task-card st-${meta.cls}${multi ? ' multi' : ''}`;
  el.dataset.key = t.key;
  el.innerHTML = `
    <div class="task-row">
      <div class="task-icon"><img class="ic" src="${IC['file' + meta.cls[0].toUpperCase() + meta.cls.slice(1)]}" alt=""></div>
      <div class="task-main">
        <div class="task-name">${escapeHtml(t.file.name)}</div>
        ${isFolder ? `<div class="task-path">${escapeHtml(t.relpath)}</div>` : ''}
      </div>
      <div class="task-side">
        <span class="task-size">${t.status === 'done' ? fmtSize(t.size) : fmtSize(t.file.size)}</span>
        <span class="task-status"><img class="ic${t.status === 'converting' ? ' spin' : ''}" src="${IC[t.status]}" alt="">${meta.text}</span>
        <span class="task-actions">
          ${t.status === 'done' ? `
            <button class="btn btn-sm btn-primary" data-act="download"><img class="ic" src="${IC.download}" alt="">下载 FBX</button>
            <button class="btn btn-sm" data-act="preview"><img class="ic" src="${IC.box}" alt="">3D 预览</button>` : ''}
          ${t.status === 'error' ? `
            <button class="btn btn-sm" data-act="retry"><img class="ic" src="${IC.refresh}" alt="">重试</button>` : ''}
          <button class="btn btn-icon" data-act="remove" title="移除"><img class="ic" src="${IC.x}" alt=""></button>
        </span>
      </div>
    </div>
    ${t.status === 'converting' ? `
      <div class="task-extra conv">
        <div class="task-stage">正在转换几何体与材质…</div>
        <div class="progress"><div class="progress-bar"></div></div>
      </div>` : ''}
    ${t.status === 'error' ? `
      <div class="task-extra">
        <div class="task-error">
          <span class="err-text">${escapeHtml(t.error || '')}</span>
          <button class="err-toggle">展开详情</button>
        </div>
      </div>` : ''}`;
  el.addEventListener('click', (e) => {
    const toggle = e.target.closest('.err-toggle');
    if (toggle) {
      const bar = toggle.closest('.task-error');
      const expanded = bar.classList.toggle('expanded');
      toggle.textContent = expanded ? '收起' : '展开详情';
      return;
    }
    const btn = e.target.closest('[data-act]');
    if (!btn) return;
    const act = btn.dataset.act;
    if (act === 'download') downloadTask(t);
    if (act === 'preview') openPreviewDrawer(t);
    if (act === 'retry') { t.status = 'queued'; t.error = null; pump(); }
    if (act === 'remove') {
      state.tasks = state.tasks.filter((x) => x.key !== t.key);
      if (state.previewTaskKey === t.key) closePreviewDrawer();
      render();
    }
  });
  return el;
}

function render() {
  const list = $('#taskList');
  list.innerHTML = '';
  for (const t of state.tasks) list.appendChild(taskCard(t));

  const total = state.tasks.length;
  const nConv = state.tasks.filter((t) => t.status === 'converting').length;
  const nDone = state.tasks.filter((t) => t.status === 'done').length;
  const nErr = state.tasks.filter((t) => t.status === 'error').length;
  $('#taskStats').innerHTML = total
    ? `共 ${total} 个<span class="sep">·</span><span class="c-conv">转换中 ${nConv}</span><span class="sep">·</span><span class="c-done">成功 ${nDone}</span><span class="sep">·</span><span class="c-err">失败 ${nErr}</span>`
    : '';

  $('#emptyState').style.display = total ? 'none' : '';
  $('#btnDownloadAll').disabled = nDone === 0;
  $('#btnClear').disabled = total === 0 || state.converting;
  updateErrorToggles();
}

function updateErrorToggles() {
  // 错误文本未省略（一行能放下）时隐藏展开/收起按钮
  requestAnimationFrame(() => {
    for (const bar of document.querySelectorAll('.task-error')) {
      const text = bar.querySelector('.err-text');
      if (!text || bar.classList.contains('expanded')) continue;
      if (text.scrollWidth <= text.clientWidth) {
        bar.classList.add('no-expand');
      } else {
        bar.classList.remove('no-expand');
      }
    }
  });
}

function escapeHtml(s) {
  return s.replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

/* ---------- 下载 ---------- */

function downloadTask(t) {
  const a = document.createElement('a');
  a.href = `/file/${t.serverId}`;
  a.download = t.file.name.replace(/\.3dxml$/i, '.fbx');
  a.click();
}

async function downloadAll() {
  const ids = state.tasks.filter((t) => t.status === 'done').map((t) => t.serverId);
  if (!ids.length) return;
  try {
    const resp = await fetch('/zip', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ids }),
    });
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      toast(data.error || '打包下载失败', 'error');
      return;
    }
    const blob = await resp.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'fbx_export.zip';
    a.click();
    URL.revokeObjectURL(a.href);
    toast(`已打包 ${ids.length} 个 FBX`, 'success');
  } catch (err) {
    toast('网络错误：' + err.message, 'error');
  }
}

/* ---------- 预览抽屉 ---------- */

async function ensurePreview() {
  if (state.preview) return state.preview;
  const mod = await import('./preview.js');
  state.preview = mod.createPreview($('#drawerViewport'), {
    onLoaded(info) {
      $('#drawerInfo').textContent =
        `顶点 ${info.verts.toLocaleString()} · 三角面 ${info.tris.toLocaleString()} · ` +
        `包围盒 ${info.size.x.toFixed(2)} × ${info.size.y.toFixed(2)} × ${info.size.z.toFixed(2)} m`;
      $('#drawerLoading').style.display = 'none';
    },
    onError() {
      $('#drawerLoading').style.display = 'none';
      toast('模型加载失败', 'error');
    },
  });
  return state.preview;
}

async function openPreviewDrawer(t) {
  state.previewTaskKey = t.key;
  $('#drawer').classList.add('open');
  document.body.classList.add('drawer-open');
  $('#drawerTitle').textContent = t.file.name.replace(/\.3dxml$/i, '.fbx');
  $('#drawerInfo').textContent = '';
  $('#drawerLoading').style.display = '';
  $('#wireframeToggle').checked = false;
  const preview = await ensurePreview();
  preview.setWireframe(false);
  preview.load(`/file/${t.serverId}`, t.file.name);
}

function closePreviewDrawer() {
  state.previewTaskKey = null;
  $('#drawer').classList.remove('open');
  document.body.classList.remove('drawer-open');
}

/* ---------- 事件绑定 ---------- */

function init() {
  const dz = $('#dropzone');
  dz.addEventListener('click', (e) => {
    if (e.target.closest('[data-pick]')) return;
    $('#fileInput').click();
  });
  $('#btnPickFile').addEventListener('click', (e) => { e.stopPropagation(); $('#fileInput').click(); });
  $('#btnPickFolder').addEventListener('click', (e) => { e.stopPropagation(); $('#folderInput').click(); });
  $('#fileInput').addEventListener('change', (e) => { handlePick(e.target.files, false); e.target.value = ''; });
  $('#folderInput').addEventListener('change', (e) => { handlePick(e.target.files, true); e.target.value = ''; });

  dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', (e) => { if (!dz.contains(e.relatedTarget)) dz.classList.remove('dragover'); });
  dz.addEventListener('drop', handleDrop);

  $('#btnDownloadAll').addEventListener('click', downloadAll);
  $('#btnClear').addEventListener('click', () => {
    openConfirm('确定清空全部任务？已转换的结果将从服务中移除引用。', () => {
      state.tasks = [];
      closePreviewDrawer();
      render();
      toast('列表已清空', 'info');
    });
  });

  $('#btnDrawerClose').addEventListener('click', closePreviewDrawer);
  $('#btnResetView').addEventListener('click', () => state.preview && state.preview.resetView());
  $('#wireframeToggle').addEventListener('change', (e) => {
    state.preview && state.preview.setWireframe(e.target.checked);
  });

  $('#helpBtn').addEventListener('click', () => $('#helpPopover').classList.toggle('open'));
  document.addEventListener('click', (e) => {
    if (!e.target.closest('#helpBtn') && !e.target.closest('#helpPopover')) {
      $('#helpPopover').classList.remove('open');
    }
  });

  $('#hostInfo').textContent = `本地服务运行中 · ${location.host}`;
  render();
}

/* ---------- 确认对话框 ---------- */

let confirmCb = null;
function openConfirm(text, cb) {
  $('#confirmText').textContent = text;
  confirmCb = cb;
  $('#confirmModal').classList.add('open');
}

document.addEventListener('DOMContentLoaded', () => {
  $('#confirmOk').addEventListener('click', () => {
    $('#confirmModal').classList.remove('open');
    confirmCb && confirmCb();
    confirmCb = null;
  });
  $('#confirmCancel').addEventListener('click', () => {
    $('#confirmModal').classList.remove('open');
    confirmCb = null;
  });
  init();
});
