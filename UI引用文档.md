# UI 引用文档（Arco UMD 离线方案）

本文档用于指导任何项目（含各类大模型/AI Agent、脚本、前后端工程）如何从站点根目录引入本 UI2 资源。请把本文件夹 `UI2/` 上传到网站根目录（例如 `https://your-site.example.com/UI2/`）。

---

## 1. 目标与能力
- 提供「无需构建、可离线」的 Arco Design（字节系）UI 能力，基于 UMD 形式。
- 只依赖原生 HTML/CSS/JS（React UMD + Arco UMD + Arco CSS），可直接在浏览器、WebView、pywebview、QtWebEngine、Electron 等容器中使用。

---

## 2. 资源地址（线上）
部署后，以下地址可直接引用：

- 样式（必需）：
  - `https://your-site.example.com/UI2/vendor/arco.index.css`
- 运行时库（必需）：
  - `https://your-site.example.com/UI2/vendor/react.production.min.js`
  - `https://your-site.example.com/UI2/vendor/react-dom.production.min.js`
  - `https://your-site.example.com/UI2/vendor/arco.min.js`

说明：
- `arco.index.css` 是 Arco 的全量样式（文件名为规范化后的本地名称）。
- `arco.min.js` 为 Arco Web React 的 UMD 入口（从官方 dist 提取）。
- 图标包 `@arco-design/icon-react` 官方不稳定提供 UMD 版本，若确需图标，推荐 npm 构建方式引入，或自行使用 SVG/IconFont。

---

## 3. 最小引用示例（直接可用）
在你的任意页面 `<head>` 与 `<body>` 末尾加入：

```html
<!-- 样式 -->
<link rel="stylesheet" href="https://your-site.example.com/UI2/vendor/arco.index.css" />

<!-- React 运行时（UMD） -->
<script src="https://your-site.example.com/UI2/vendor/react.production.min.js"></script>
<script src="https://your-site.example.com/UI2/vendor/react-dom.production.min.js"></script>

<!-- Arco 组件库（UMD） -->
<script src="https://your-site.example.com/UI2/vendor/arco.min.js"></script>

<!-- 根节点 -->
<div id="root"></div>

<!-- 启动脚本 -->
<script>
  // 兼容多种 UMD 全局命名
  const Arco =
    window.arco ||
    window.Arco ||
    window['@arco-design/web-react'] ||
    window.ArcoDesign || {};

  const { Button, Table } = Arco;
  if (!Button || !Table) {
    document.getElementById('root').innerHTML =
      '<div style="padding:16px;color:#c00;font-weight:600">Arco UMD 未加载，请检查 script 引用路径。</div>';
  } else {
    const columns = [
      { title: 'ID', dataIndex: 'id' },
      { title: '备注', dataIndex: 'remark' },
      { title: '代理', dataIndex: 'proxy' },
    ];
    const data = [
      { id: 1, remark: '示例-1', proxy: '直连' },
      { id: 2, remark: '示例-2', proxy: 'socks5://127.0.0.1:1080' },
    ];

    const App = () => React.createElement('div', { style: { padding: 16 } },
      React.createElement(Button, { type: 'primary', onClick: () => alert('Hello Arco!') }, '测试按钮'),
      React.createElement('div', { style: { height: 12 } }),
      React.createElement(Table, { columns, data })
    );

    ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
  }
</script>
```

本示例不依赖任何构建工具；可在浏览器、本地 WebView、pywebview 等环境直接打开。

---

## 4. 推荐页面结构与样式约定
- 页面基础结构：
  - 顶部工具条（操作按钮、导航）
  - 侧边导航（可选）
  - 内容区使用「卡片 + 表格/表单」形式（企业后台风格）
- 主题与色彩：Arco 默认蓝色主题适合企业后台；必要时可在后续扩展自定义主题。

---

## 5. 在不同容器的使用方式
- 纯浏览器：直接使用上面的引入片段。
- pywebview / QtWebEngine / CEF / Electron：
  - 加载你的本地 `index.html` 或远程 URL 页面
  - 与 Python/后端通信用 `window.pywebview.api.xxx()` 或原生 IPC/HTTP 接口
  - 推荐把数据拉取/写入封装为函数，前端只负责调用

---

## 6. 目录结构（发布后）
```
/UI2/
  ├─ index.html                 # 示例（可删除/替换为你的页面）
  └─ vendor/
       ├─ react.production.min.js
       ├─ react-dom.production.min.js
       ├─ arco.min.js
       └─ arco.index.css
```

---

## 7. 缓存与版本策略
- 建议在引用 URL 后附加版本参数（便于更新）：
  - 例：`https://your-site.example.com/UI2/vendor/arco.min.js?v=20251113`
- 更新资源时同步更新时间戳（或使用服务端静态资源 hash 命名）

---

## 8. 常见问题（FAQ）
1) 报错 `Cannot destructure property 'Button' ... is undefined`  
   - 原因：`arco.min.js` 未正确加载或 UMD 全局名不同；按示例中的多重兜底获取全局对象；同时检查网络路径是否 200、是否被 CSP 拦截。
2) 样式未生效  
   - 检查 `arco.index.css` 是否加载（网络面板 200），或者是否被覆盖；尽量将 link 放在 head 顶部。
3) 图标组件缺失  
   - UMD 场景官方不稳定提供图标 UMD 包，建议：
     - 使用 SVG/IconFont；或
     - 采用 npm 构建方式引入 `@arco-design/icon-react`。
4) 本地 file:// 打开报 CORS/路径问题  
   - 推荐部署到站点或通过本地静态服务器（例如 `npx serve` / `python -m http.server`）打开；或在桌面容器（pywebview）中加载相对路径。

---

## 9. 与后端/API 的约定（建议）
- 统一返回 JSON：`{ ok: true, data: ..., error: "" }`
- 典型交互：
  - 列表：`GET /api/profiles`
  - 新增：`POST /api/profiles`（remark, proxy, default_url...）
  - 打开/清理/克隆/删除：`POST /api/profiles/:id/actions` 指明 action
- 前端只做展示与调用；权限/校验/日志在后端完成

---

## 10. 版本与更新说明
- 当前 UMD 资源为稳定可用的组合：React 18 + Arco（dist UMD）+ 样式 `arco.css`（重命名为 `arco.index.css`）。
- 如需升级：先在测试环境替换 `vendor/` 文件并验证，再更新线上文件与版本参数。

---

## 11. 版权与许可
- Arco Design 组件库与样式遵循 MIT 许可；React 遵循自身许可；请遵守其开源协议。

---

## 12. 供 AI/大模型读取的要点摘要
- 引入 4 个文件并使用 UMD 全局对象：
  - CSS：`/UI2/vendor/arco.index.css`
  - JS：`/UI2/vendor/react.production.min.js`、`/UI2/vendor/react-dom.production.min.js`、`/UI2/vendor/arco.min.js`
- 全局对象名称兼容获取：
  - `window.arco || window.Arco || window['@arco-design/web-react'] || window.ArcoDesign`
- 组件使用：
  - `const { Button, Table } = ArcoGlobal; ReactDOM.createRoot(...).render(React.createElement(Button, ...))`
- 图标：UMD 不保证提供；需则用 npm 构建或 SVG/IconFont。
- 缓存：在 URL 后添加 `?v=时间戳` 进行缓存刷新。

---

如需进一步本地化主题或生成更多示例页面，可在 `UI2/` 下添加你的页面与资源，并按以上规范引用。*** End Patch


